"""Tests that end_run adds one memory extract outbox event only when a run completes, on the real database."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.enums import OutboxEventType, RunStatus
from app.db.models import AgentRun, Conversation, Message, OutboxEvent, User
from app.db.session import SessionLocal, engine
from app.features.runs.repository import RunRepository
from app.features.runs.worker import end_run


@dataclass
class SeededRun:

    """The ids of a temp user, conversation, queued run and its assistant message."""

    user_id: int
    conversation_id: int
    run_id: int
    assistant_message_id: int


@pytest.fixture
async def seeded_run() -> AsyncIterator[SeededRun]:

    """Create a temp user with one queued run, then delete every row it made and close the pool."""

    async with SessionLocal() as session:

        user = User(name="Outbox Test", email=f"outbox-test-{uuid4().hex}@example.com")

        session.add(user)

        await session.flush()

        repository = RunRepository(session)

        conversation = await repository.create_conversation(user.id, "Outbox test")

        run, _, assistant_message = await repository.create_run_with_messages(
            conversation.id,
            uuid4().hex,
            "I avoid tobacco stocks",
            )

        await session.commit()

        seeded = SeededRun(user.id, conversation.id, run.id, assistant_message.id)

    try:
        yield seeded

    finally:

        async with SessionLocal() as session:

            await session.execute(delete(OutboxEvent).where(OutboxEvent.user_id == seeded.user_id))
            await session.execute(delete(Message).where(Message.conversation_id == seeded.conversation_id))
            await session.execute(delete(AgentRun).where(AgentRun.conversation_id == seeded.conversation_id))
            await session.execute(delete(Conversation).where(Conversation.id == seeded.conversation_id))
            await session.execute(delete(User).where(User.id == seeded.user_id))

            await session.commit()

        await engine.dispose()


async def finish(
    seeded: SeededRun,
    final_status: RunStatus,
    ) -> None:

    """Call end_run for the seeded run with the given final status."""

    await end_run(
        seeded.run_id,
        seeded.conversation_id,
        seeded.user_id,
        seeded.assistant_message_id,
        final_status,
        "Noted, I will leave out tobacco.",
        )


async def outbox_rows(run_id: int) -> list[OutboxEvent]:

    """Return every outbox event keyed on this run."""

    async with SessionLocal() as session:

        result = await session.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_id == run_id))

        return list(result)


async def test_completed_run_adds_one_memory_extract_event(seeded_run: SeededRun) -> None:

    """A completed run commits exactly one pending memory.extract.requested event with ids in its payload."""

    await finish(seeded_run, RunStatus.completed)

    rows = await outbox_rows(seeded_run.run_id)

    assert len(rows) == 1
    assert rows[0].event_type == OutboxEventType.memory_extract_requested
    assert rows[0].aggregate_type == "agent_run"
    assert rows[0].user_id == seeded_run.user_id
    assert rows[0].payload == {
        "event_version": 1,
        "user_id": seeded_run.user_id,
        "conversation_id": seeded_run.conversation_id,
        "run_id": seeded_run.run_id,
        }


async def test_failed_run_adds_no_event(seeded_run: SeededRun) -> None:

    """A failed run commits no outbox event."""

    await finish(seeded_run, RunStatus.failed)

    assert await outbox_rows(seeded_run.run_id) == []


async def test_ending_twice_keeps_one_event(seeded_run: SeededRun) -> None:

    """Calling end_run again on an ended run adds no second event."""

    await finish(seeded_run, RunStatus.completed)
    await finish(seeded_run, RunStatus.completed)

    assert len(await outbox_rows(seeded_run.run_id)) == 1
