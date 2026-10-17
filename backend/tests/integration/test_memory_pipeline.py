"""End-to-end tests for the memory pipe: run end, outbox, publisher, Redis stream and worker, on real Postgres and Redis."""

import pytest
from sqlalchemy import func, select

from app.core.redis import ensure_group, get_redis, read_group
from app.db.enums import MemoryStatus, MessageRole, OutboxStatus, RunStatus
from app.db.models import AgentRun, MemoryItem, Message, OutboxEvent
from app.db.session import SessionLocal
from app.features.memory import extractor, worker
from app.features.memory.repository import MemoryRepository
from app.features.memory.schemas import MemoryCandidate, MemorySource
from app.features.outbox import publisher
from app.features.outbox.repository import OutboxRepository
from app.features.runs.worker import end_run
from tests.support import SeededRun, create_user, delete_user_data


GROUP = "memory-workers-test"

CONSUMER = "memory-worker-test"


async def fake_extract(
    messages: list[Message],
    memories: list[MemoryItem],
    ) -> list[MemoryCandidate]:

    """Stand in for the LLM, finding one tobacco preference in the user's message."""

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


async def complete(seeded: SeededRun) -> None:

    """End the seeded run as completed, which commits its outbox event."""

    await end_run(
        seeded.run_id,
        seeded.conversation_id,
        seeded.user_id,
        seeded.assistant_message_id,
        RunStatus.completed,
        "Noted, I will leave out tobacco.",
        )


async def outbox_row(run_id: int) -> OutboxEvent | None:

    """Return the outbox event keyed on this run, if any."""

    async with SessionLocal() as session:
        return await session.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == run_id))


async def user_memories(user_id: int) -> list[MemoryItem]:

    """Return the user's memory rows, oldest first."""

    async with SessionLocal() as session:
        return list(await session.scalars(select(MemoryItem).where(MemoryItem.user_id == user_id).order_by(MemoryItem.id)))


async def pending_count(stream: str) -> int:

    """Return how many entries the test group has handed out but not acknowledged."""

    return (await get_redis().xpending(stream, GROUP))["pending"]


async def test_completed_run_flows_into_memory(
    seeded_run: SeededRun,
    redis_stream: str,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """A completed run's event is published, consumed and saved as an active memory, then acknowledged."""

    async with SessionLocal() as session:

        others = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.pending, OutboxEvent.user_id != seeded_run.user_id)
            )

    if others:
        pytest.skip("real pending outbox rows exist; the publisher would send them to the test stream")

    monkeypatch.setattr(worker, "extract_candidates", fake_extract)

    await ensure_group(redis_stream, GROUP)

    await complete(seeded_run)

    assert await publisher.publish_batch(redis_stream) == 1
    assert await worker.run_once(redis_stream, GROUP, CONSUMER, claim_idle_ms=0, block_ms=None) == 1

    row = await outbox_row(seeded_run.run_id)
    [memory] = await user_memories(seeded_run.user_id)

    assert row.status == OutboxStatus.published
    assert memory.status == MemoryStatus.active
    assert memory.source_run_id == seeded_run.run_id
    assert memory.source_message_id == seeded_run.user_message_id
    assert await pending_count(redis_stream) == 0


async def test_restart_replays_own_pending_entry(
    seeded_run: SeededRun,
    redis_stream: str,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """An entry the worker read but never acknowledged before a crash is processed at once on the next start."""

    monkeypatch.setattr(worker, "extract_candidates", fake_extract)

    await ensure_group(redis_stream, GROUP)

    await complete(seeded_run)

    await get_redis().xadd(redis_stream, publisher.stream_fields(await outbox_row(seeded_run.run_id)))

    assert len(await read_group(redis_stream, GROUP, CONSUMER, 10, None)) == 1
    assert await pending_count(redis_stream) == 1

    assert await worker.replay_pending(redis_stream, GROUP, CONSUMER) == 1

    assert len(await user_memories(seeded_run.user_id)) == 1
    assert await pending_count(redis_stream) == 0


async def test_error_before_commit_leaves_no_outbox_event(
    seeded_run: SeededRun,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """A crash after the outbox insert but before commit rolls back both the run end and the event."""

    original = OutboxRepository.add_memory_extract

    async def insert_then_crash(self: OutboxRepository, *args: int) -> int | None:

        """Insert the event like the real method, then fail before end_run can commit."""

        await original(self, *args)

        raise RuntimeError("crash before commit")

    monkeypatch.setattr(OutboxRepository, "add_memory_extract", insert_then_crash)

    with pytest.raises(RuntimeError):
        await complete(seeded_run)

    async with SessionLocal() as session:
        run = await session.get_one(AgentRun, seeded_run.run_id)

    assert run.status == RunStatus.queued
    assert await outbox_row(seeded_run.run_id) is None


async def test_event_for_wrong_user_saves_nothing(
    seeded_run: SeededRun,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """An event whose user does not own the run reads no messages, never calls the LLM and saves nothing."""

    monkeypatch.setattr(extractor.llm_service, "get_model", lambda name: pytest.fail("LLM was called"))

    other_user_id = await create_user()

    try:

        await complete(seeded_run)

        row = await outbox_row(seeded_run.run_id)

        payload = {**row.payload, "user_id": other_user_id}

        await worker.handle_memory_extract(row.id, payload)

        assert await user_memories(other_user_id) == []
        assert await user_memories(seeded_run.user_id) == []

    finally:
        await delete_user_data(other_user_id)


async def test_active_memories_are_per_user(seeded_run: SeededRun) -> None:

    """The extractor is only shown the memories of the event's own user."""

    other_user_id = await create_user()

    try:

        async with SessionLocal() as session:

            outbox_event_id = await OutboxRepository(session).add_memory_extract(
                seeded_run.run_id,
                seeded_run.conversation_id,
                seeded_run.user_id,
                )

            repository = MemoryRepository(session)

            for user_id, sectors in ((seeded_run.user_id, ["tobacco"]), (other_user_id, ["alcohol"])):

                source = MemorySource(user_id, seeded_run.conversation_id, seeded_run.run_id, outbox_event_id)

                await repository.save_candidate(
                    MemoryCandidate("preference", "investment_preferences", "excluded_sectors", {"sectors": sectors}),
                    source,
                    )

            await session.commit()

            mine = await repository.active_memories(seeded_run.user_id)

        assert [memory.content for memory in mine] == [{"sectors": ["tobacco"]}]

    finally:
        await delete_user_data(other_user_id)
