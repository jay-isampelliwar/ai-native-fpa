"""Tests that the memory worker saves memories, skips redeliveries, retries failures and dead letters them, on real Postgres and Redis."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from sqlalchemy import select

from app.core.redis import ensure_group, get_redis
from app.db.enums import MemoryEventType, MemoryStatus, MessageRole
from app.db.models import MemoryEvent, MemoryItem, Message, OutboxEvent
from app.db.session import SessionLocal
from app.features.memory import worker
from app.features.memory.repository import MemoryRepository
from app.features.memory.schemas import MemoryCandidate, MemorySource
from app.features.outbox.publisher import stream_fields
from app.features.outbox.repository import OutboxRepository
from tests.support import SeededRun


GROUP = "memory-workers-test"

CONSUMER = "memory-worker-test"


@dataclass
class Seeded:

    """The ids and stream a test works with."""

    stream: str
    user_id: int
    conversation_id: int
    run_id: int
    outbox_event_id: int
    fields: dict[str, str]


@pytest.fixture
async def seeded(
    seeded_run: SeededRun,
    redis_stream: str,
    ) -> AsyncIterator[Seeded]:

    """Add a memory extract outbox event to the seeded run and a consumer group on the test stream."""

    async with SessionLocal() as session:

        outbox_event_id = await OutboxRepository(session).add_memory_extract(
            seeded_run.run_id,
            seeded_run.conversation_id,
            seeded_run.user_id,
            )

        await session.commit()

        event = await session.get_one(OutboxEvent, outbox_event_id)

        fields = stream_fields(event)

    await ensure_group(redis_stream, GROUP)

    yield Seeded(
        redis_stream,
        seeded_run.user_id,
        seeded_run.conversation_id,
        seeded_run.run_id,
        outbox_event_id,
        fields,
        )


def candidate(sectors: list[str]) -> MemoryCandidate:

    """A preference memory for excluded sectors."""

    return MemoryCandidate(
        memory_type="preference",
        namespace="investment_preferences",
        memory_key="excluded_sectors",
        content={"sectors": sectors},
        )


async def fake_extract(
    messages: list[Message],
    memories: list[MemoryItem],
    ) -> list[MemoryCandidate]:

    """Stand in for the LLM extractor, finding one tobacco preference in the user's message."""

    user_message = next(message for message in messages if message.role == MessageRole.user)

    return [
        MemoryCandidate(
            memory_type="preference",
            namespace="investment_preferences",
            memory_key="excluded_sectors",
            content={"sectors": ["tobacco"]},
            source_message_id=user_message.id,
            )
        ]


async def broken_extract(
    messages: list[Message],
    memories: list[MemoryItem],
    ) -> list[MemoryCandidate]:

    """Stand in for an extractor that always fails."""

    raise RuntimeError("extractor is down")


async def run_once(data: Seeded) -> int:

    """Run one worker pass on the test stream, retrying pending entries at once and not blocking."""

    return await worker.run_once(data.stream, GROUP, CONSUMER, claim_idle_ms=0, block_ms=None)


async def pending_count(data: Seeded) -> int:

    """Return how many entries the test group has handed out but not acknowledged."""

    return (await get_redis().xpending(data.stream, GROUP))["pending"]


async def memories(user_id: int) -> tuple[list[MemoryItem], list[MemoryEvent]]:

    """Return the user's memory rows and history rows, oldest first."""

    async with SessionLocal() as session:

        items = await session.scalars(select(MemoryItem).where(MemoryItem.user_id == user_id).order_by(MemoryItem.id))
        events = await session.scalars(select(MemoryEvent).where(MemoryEvent.user_id == user_id).order_by(MemoryEvent.id))

        return list(items), list(events)


async def test_valid_event_saves_memory_and_acks(
    seeded: Seeded,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """One extract event saves an active memory and a created history row with its sources, then is acknowledged."""

    monkeypatch.setattr(worker, "extract_candidates", fake_extract)

    await get_redis().xadd(seeded.stream, seeded.fields)

    assert await run_once(seeded) == 1

    items, events = await memories(seeded.user_id)

    assert len(items) == 1
    assert items[0].status == MemoryStatus.active
    assert items[0].content == {"sectors": ["tobacco"]}
    assert items[0].source_run_id == seeded.run_id
    assert items[0].source_message_id is not None

    assert len(events) == 1
    assert events[0].event_type == MemoryEventType.created
    assert events[0].outbox_event_id == seeded.outbox_event_id

    assert await pending_count(seeded) == 0


async def test_redelivered_event_creates_no_duplicate(
    seeded: Seeded,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """The same outbox event arriving twice saves its memory only once and acknowledges both entries."""

    monkeypatch.setattr(worker, "extract_candidates", fake_extract)

    await get_redis().xadd(seeded.stream, seeded.fields)
    await get_redis().xadd(seeded.stream, seeded.fields)

    await run_once(seeded)

    items, events = await memories(seeded.user_id)

    assert len(items) == 1
    assert len(events) == 1
    assert await pending_count(seeded) == 0


async def test_same_key_supersedes_old_memory(seeded: Seeded) -> None:

    """Saving a memory with an active key marks the old one superseded and keeps both in history."""

    source = MemorySource(seeded.user_id, seeded.conversation_id, seeded.run_id, seeded.outbox_event_id)

    async with SessionLocal() as session:

        repository = MemoryRepository(session)

        await repository.save_candidate(candidate(["tobacco"]), source)
        await repository.save_candidate(candidate(["tobacco", "gambling"]), source)

        await session.commit()

    items, events = await memories(seeded.user_id)

    assert [item.status for item in items] == [MemoryStatus.superseded, MemoryStatus.active]
    assert items[1].content == {"sectors": ["tobacco", "gambling"]}
    assert [event.event_type for event in events] == [
        MemoryEventType.created,
        MemoryEventType.superseded,
        MemoryEventType.created,
        ]


async def test_failed_event_stays_pending(
    seeded: Seeded,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """A failing handler saves nothing and leaves the entry pending for a later retry."""

    monkeypatch.setattr(worker, "extract_candidates", broken_extract)

    await get_redis().xadd(seeded.stream, seeded.fields)

    await run_once(seeded)

    items, _ = await memories(seeded.user_id)

    assert items == []
    assert await pending_count(seeded) == 1


async def test_sixth_delivery_goes_to_dead_stream(
    seeded: Seeded,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """An entry that fails on five deliveries is moved to the dead stream and acknowledged on the sixth."""

    monkeypatch.setattr(worker, "extract_candidates", broken_extract)

    await get_redis().xadd(seeded.stream, seeded.fields)

    for _ in range(5):
        await run_once(seeded)

    assert await pending_count(seeded) == 1
    assert await get_redis().xlen(worker.dead_stream(seeded.stream)) == 0

    await run_once(seeded)

    dead = await get_redis().xrange(worker.dead_stream(seeded.stream))

    assert await pending_count(seeded) == 0
    assert len(dead) == 1
    assert dead[0][1]["event_id"] == str(seeded.outbox_event_id)


async def test_unknown_event_type_is_acked(seeded: Seeded) -> None:

    """An event type with no handler is acknowledged and saves nothing."""

    await get_redis().xadd(seeded.stream, {**seeded.fields, "event_type": "memory.summary.requested"})

    await run_once(seeded)

    items, _ = await memories(seeded.user_id)

    assert items == []
    assert await pending_count(seeded) == 0
