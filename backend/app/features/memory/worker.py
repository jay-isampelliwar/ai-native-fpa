"""The memory worker: a process that reads memory events from the Redis stream under its own consumer name, saves memories in Postgres, then acknowledges them."""

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

import orjson

from app.core.config import get_settings
from app.core.redis import (
    ack,
    claim_stale,
    close_redis,
    delivery_count,
    ensure_group,
    process_name,
    prune_consumers,
    publish_event,
    read_group,
    )
from app.db.enums import OutboxEventType
from app.db.session import SessionLocal, engine
from app.features.memory.extractor import extract_candidates
from app.features.memory.repository import MemoryRepository
from app.features.memory.schemas import MemorySource
from app.observability.langfuse import shutdown_langfuse, start_langfuse


log = logging.getLogger(__name__)

BLOCK_MS = 5000

ERROR_SLEEP_SECONDS = 1.0

Handler = Callable[[int, dict[str, Any]], Awaitable[None]]


def dead_stream(stream: str) -> str:

    """Name the stream where entries that failed too often are kept."""

    return f"{stream}:dead"


async def handle_memory_extract(
    event_id: int,
    payload: dict[str, Any],
    ) -> None:

    """Read one completed run, extract its memories and save them with history in one commit, unless already done."""

    source = MemorySource(
        user_id=payload["user_id"],
        conversation_id=payload["conversation_id"],
        run_id=payload["run_id"],
        outbox_event_id=event_id,
        )

    async with SessionLocal() as session:

        repository = MemoryRepository(session)

        if await repository.already_processed(event_id):

            log.info("memory event %s already processed, skipping", event_id)

            return

        messages = await repository.run_messages(source.run_id, source.user_id)
        memories = await repository.active_memories(source.user_id)

        candidates = await extract_candidates(messages, memories)

        for candidate in candidates:
            await repository.save_candidate(candidate, source)

        await session.commit()

    log.info("memory event %s saved %s memories for run %s", event_id, len(candidates), source.run_id)


HANDLERS: dict[str, Handler] = {
    OutboxEventType.memory_extract_requested.value: handle_memory_extract,
    }


async def process_entry(
    stream: str,
    group: str,
    entry_id: str,
    fields: dict[str, str],
    ) -> None:

    """Run the entry's handler and acknowledge it only after Postgres commits, leaving it pending if the handler fails."""

    handler = HANDLERS.get(fields.get("event_type", ""))

    if handler is None:

        log.warning("no handler for stream entry %s of type %s, acknowledging", entry_id, fields.get("event_type"))

        await ack(stream, group, entry_id)

        return

    try:
        await handler(int(fields["event_id"]), orjson.loads(fields["payload"]))

    except Exception:

        log.exception("stream entry %s failed, leaving it pending for retry", entry_id)

        return

    await ack(stream, group, entry_id)


async def dead_letter_if_exhausted(
    stream: str,
    group: str,
    entry_id: str,
    fields: dict[str, str],
    ) -> bool:

    """Move an entry delivered more times than the retry limit to the dead stream and acknowledge it, returning True if moved."""

    if await delivery_count(stream, group, entry_id) <= get_settings().MEMORY_WORKER_RETRY_LIMIT:
        return False

    await publish_event(dead_stream(stream), {**fields, "source_entry_id": entry_id})
    await ack(stream, group, entry_id)

    log.error("stream entry %s failed too often, moved to %s", entry_id, dead_stream(stream))

    return True


async def run_once(
    stream: str,
    group: str,
    consumer: str,
    claim_idle_ms: int | None = None,
    block_ms: int | None = BLOCK_MS,
    ) -> int:

    """Retry stale pending entries, then read and process new ones, and return how many entries it handled."""

    settings = get_settings()

    if claim_idle_ms is None:
        claim_idle_ms = settings.MEMORY_WORKER_CLAIM_AFTER_SECONDS * 1000

    claimed = await claim_stale(stream, group, consumer, claim_idle_ms, settings.MEMORY_WORKER_BATCH_SIZE)

    for entry_id, fields in claimed:

        if await dead_letter_if_exhausted(stream, group, entry_id, fields):
            continue

        await process_entry(stream, group, entry_id, fields)

    fresh = await read_group(stream, group, consumer, settings.MEMORY_WORKER_BATCH_SIZE, block_ms)

    for entry_id, fields in fresh:
        await process_entry(stream, group, entry_id, fields)

    return len(claimed) + len(fresh)


async def replay_pending(
    stream: str,
    group: str,
    consumer: str,
    ) -> int:

    """On startup, process every entry this consumer read but never acknowledged before it stopped, and return how many."""

    batch_size = get_settings().MEMORY_WORKER_BATCH_SIZE
    last_id = "0"
    replayed = 0

    while True:

        entries = await read_group(stream, group, consumer, batch_size, None, start_id=last_id)

        if not entries:
            return replayed

        for entry_id, fields in entries:

            if not await dead_letter_if_exhausted(stream, group, entry_id, fields):
                await process_entry(stream, group, entry_id, fields)

        last_id = entries[-1][0]
        replayed += len(entries)


async def start(
    stream: str,
    group: str,
    consumer: str,
    ) -> None:

    """Create the group, delete old idle consumers, and replay this consumer's unfinished entries, retrying until Redis is reachable."""

    while True:

        try:

            await ensure_group(stream, group)

            pruned = await prune_consumers(stream, group, consumer, get_settings().REDIS_CONSUMER_PRUNE_AFTER_SECONDS * 1000)

            if pruned:
                log.info("memory worker deleted idle consumers %s", pruned)

            replayed = await replay_pending(stream, group, consumer)

            break

        except Exception:

            log.exception("memory worker could not start, retrying")

            await asyncio.sleep(ERROR_SLEEP_SECONDS)

    log.info("memory worker %s started on %s, replayed %s pending entries", consumer, stream, replayed)


async def consume_forever() -> None:

    """Start under this process's own consumer name, then process entries until cancelled, without closing any pool."""

    settings = get_settings()
    stream = settings.REDIS_MEMORY_STREAM
    group = settings.REDIS_MEMORY_CONSUMER_GROUP
    consumer = process_name()

    await start(stream, group, consumer)

    while True:

        try:
            await run_once(stream, group, consumer)

        except Exception:

            log.exception("memory worker loop failed")

            await asyncio.sleep(ERROR_SLEEP_SECONDS)


async def run_forever() -> None:

    """Start this process's Langfuse client, run the worker until stopped, and close Redis and the DB pool on exit."""

    start_langfuse(get_settings())

    try:
        await consume_forever()

    finally:

        shutdown_langfuse(get_settings())

        await close_redis()
        await engine.dispose()

        log.info("memory worker stopped")


async def main() -> None:

    """Run the worker, stopping it the same way on SIGTERM as on Ctrl+C."""

    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, asyncio.current_task().cancel)

    with suppress(asyncio.CancelledError):
        await run_forever()


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    with suppress(KeyboardInterrupt):
        asyncio.run(main())
