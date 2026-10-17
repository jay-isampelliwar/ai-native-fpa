"""Tests that the outbox publisher moves pending events into a Redis stream, retries failures and dead letters them, on real Postgres and Redis."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import orjson
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import delete, func, select

from app.core.redis import close_redis, get_redis
from app.db.enums import OutboxEventType, OutboxStatus
from app.db.models import OutboxEvent
from app.db.session import SessionLocal, engine
from app.features.outbox import publisher


TEST_AGGREGATE = "publisher_test"


@pytest.fixture
async def stream() -> AsyncIterator[str]:

    """Give each test its own Redis stream, then delete it with the test's outbox rows and close both pools."""

    async with SessionLocal() as session:

        others = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.pending, OutboxEvent.aggregate_type != TEST_AGGREGATE)
            )

    if others:
        pytest.skip("real pending outbox rows exist; the publisher would send them to the test stream")

    name = f"ai-native-fpa:test:{uuid4().hex}"

    try:
        yield name

    finally:

        async with SessionLocal() as session:

            await session.execute(delete(OutboxEvent).where(OutboxEvent.aggregate_type == TEST_AGGREGATE))

            await session.commit()

        await get_redis().delete(name)
        await close_redis()
        await engine.dispose()


async def add_pending(
    attempts: int = 0,
    available_at: datetime | None = None,
    ) -> int:

    """Insert one pending test event and return its id."""

    async with SessionLocal() as session:

        event = OutboxEvent(
            event_type=OutboxEventType.memory_extract_requested,
            aggregate_type=TEST_AGGREGATE,
            aggregate_id=int(uuid4().int % 10**12),
            payload={"event_version": 1, "run_id": 42},
            attempts=attempts,
            )

        if available_at is not None:
            event.available_at = available_at

        session.add(event)

        await session.commit()

        return event.id


async def load(event_id: int) -> OutboxEvent:

    """Read one outbox row fresh from the database."""

    async with SessionLocal() as session:

        return await session.get_one(OutboxEvent, event_id)


async def fail_publish(
    stream: str,
    fields: dict[str, str],
    ) -> str:

    """Stand in for publish_event when Redis is down."""

    raise RedisConnectionError("redis is down")


async def test_pending_event_is_published_to_stream(stream: str) -> None:

    """A due pending row lands in the stream with its id, type and payload, and is marked published."""

    event_id = await add_pending()

    assert await publisher.publish_batch(stream) == 1

    entries = await get_redis().xrange(stream)

    assert len(entries) == 1

    _, fields = entries[0]

    assert fields["event_id"] == str(event_id)
    assert fields["event_type"] == "memory.extract.requested"
    assert orjson.loads(fields["payload"]) == {"event_version": 1, "run_id": 42}

    row = await load(event_id)

    assert row.status == OutboxStatus.published
    assert row.processed_at is not None


async def test_redis_failure_schedules_retry(
    stream: str,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """A Redis error keeps the row pending, counts the attempt and pushes available_at about two seconds out."""

    monkeypatch.setattr(publisher, "publish_event", fail_publish)

    event_id = await add_pending()
    before = datetime.now(UTC)

    await publisher.publish_batch(stream)

    row = await load(event_id)

    assert row.status == OutboxStatus.pending
    assert row.attempts == 1
    assert row.last_error == "redis is down"
    assert row.available_at >= before + timedelta(seconds=1)


async def test_fifth_failure_dead_letters(
    stream: str,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """A row that already failed four times becomes dead_letter on the fifth failure."""

    monkeypatch.setattr(publisher, "publish_event", fail_publish)

    event_id = await add_pending(attempts=4)

    await publisher.publish_batch(stream)

    row = await load(event_id)

    assert row.status == OutboxStatus.dead_letter
    assert row.attempts == 5


async def test_future_event_is_skipped(stream: str) -> None:

    """A row waiting for its retry time is not taken, and nothing reaches the stream."""

    event_id = await add_pending(available_at=datetime.now(UTC) + timedelta(minutes=5))

    assert await publisher.publish_batch(stream) == 0
    assert await get_redis().xlen(stream) == 0

    row = await load(event_id)

    assert row.status == OutboxStatus.pending
