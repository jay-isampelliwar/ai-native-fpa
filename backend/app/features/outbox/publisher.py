"""The outbox publisher: a loop that moves pending outbox events from Postgres into the Redis memory stream."""

import asyncio
import logging
from contextlib import suppress

import orjson
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.redis import close_redis, publish_event
from app.db.models import OutboxEvent
from app.db.session import SessionLocal, engine
from app.features.outbox.repository import OutboxRepository


log = logging.getLogger(__name__)


def stream_fields(event: OutboxEvent) -> dict[str, str]:

    """Turn an outbox row into the flat string fields one Redis stream entry holds."""

    return {
        "event_id": str(event.id),
        "event_type": event.event_type.value,
        "payload": orjson.dumps(event.payload).decode(),
        }


async def publish_batch(stream: str | None = None) -> int:

    """Send one batch of due pending events to the stream, mark each published or retried, and return how many it took."""

    settings = get_settings()
    stream = stream or settings.REDIS_MEMORY_STREAM

    async with SessionLocal() as session:

        repository = OutboxRepository(session)

        events = await repository.claim_pending(settings.MEMORY_WORKER_BATCH_SIZE)

        for event in events:

            try:
                await publish_event(stream, stream_fields(event))

            except RedisError as exc:

                log.warning("outbox event %s failed to publish: %s", event.id, exc)

                repository.mark_retry(event, str(exc), settings.MEMORY_WORKER_RETRY_LIMIT)

                continue

            repository.mark_published(event)

        await session.commit()

    return len(events)


async def run_forever() -> None:

    """Publish batches until stopped, resting when nothing is due, and close Redis and the DB pool on exit."""

    settings = get_settings()
    batch_size = settings.MEMORY_WORKER_BATCH_SIZE

    log.info("outbox publisher started")

    try:

        while True:

            try:
                taken = await publish_batch()

            except Exception:

                log.exception("outbox publisher batch failed")

                taken = 0

            if taken < batch_size:
                await asyncio.sleep(settings.OUTBOX_IDLE_SLEEP_SECONDS)

    finally:

        await close_redis()
        await engine.dispose()

        log.info("outbox publisher stopped")


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    with suppress(KeyboardInterrupt):
        asyncio.run(run_forever())
