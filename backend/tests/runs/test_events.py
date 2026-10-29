"""Tests that run events are numbered, saved and replayed after a reconnect, that live events follow on, and that a saved cancel stops a run, on real Postgres and Redis."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from app.agent.cancellation import RunCancelled, stop_if_cancelled
from app.db.enums import RunStatus
from app.db.models import AgentRun, RunEventRecord
from app.db.session import SessionLocal
from app.features.runs.events import (
    ASSISTANT_DELTA,
    ASSISTANT_SNAPSHOT,
    RUN_COMPLETED,
    TOOL_FINISHED,
    TOOL_STARTED,
    RunEvent,
    )
from app.features.runs.publisher import RunPublisher
from app.features.runs.repository import RunEventRepository
from app.features.runs.stream import follow
from tests.support import SeededRun


TOOL = {"id": "call-1", "name": "list_records", "label": "Reading your records"}


def parse(block: str) -> tuple[int | None, str]:

    """Read the id and the event name out of one server-sent event block."""

    lines = dict(line.split(": ", 1) for line in block.strip().split("\n"))

    seq = int(lines["id"]) if "id" in lines else None

    return seq, lines["event"]


async def collect(run_id: int, after: int) -> list[tuple[int | None, str]]:

    """Follow the run from after to its end and return each event's id and name."""

    return [parse(block) async for block in follow(run_id, after) if not block.startswith(":")]


async def saved_rows(run_id: int) -> list[RunEventRecord]:

    """Return the run's saved event rows in order."""

    async with SessionLocal() as session:
        return await RunEventRepository(session).list_after(run_id, 0)


async def set_status(run_id: int, status: RunStatus) -> None:

    """Overwrite the run's status."""

    async with SessionLocal() as session:

        await session.execute(update(AgentRun).where(AgentRun.id == run_id).values(status=status))

        await session.commit()


async def publish_turn(run_id: int) -> RunPublisher:

    """Publish a tool step, two reply pieces, the tool's end, one more piece and completion, as a worker would."""

    publisher = await RunPublisher(run_id).open()

    await publisher.emit(RunEvent(TOOL_STARTED, TOOL))
    await publisher.emit(RunEvent(ASSISTANT_DELTA, {"text": "You spent "}))
    await publisher.emit(RunEvent(ASSISTANT_DELTA, {"text": "25000 "}))
    await publisher.emit(RunEvent(TOOL_FINISHED, {**TOOL, "status": "ok"}))
    await publisher.emit(RunEvent(ASSISTANT_DELTA, {"text": "on rent."}))
    await publisher.emit(RunEvent(RUN_COMPLETED, {"text": "You spent 25000 on rent."}))

    return publisher


async def test_pieces_are_grouped_and_steps_saved_alone(seeded_run: SeededRun) -> None:

    """Reply pieces are saved as one row per group, numbered as their last piece, and every other event as its own row."""

    await publish_turn(seeded_run.run_id)

    rows = await saved_rows(seeded_run.run_id)

    assert [(row.seq, row.event_type) for row in rows] == [
        (1, TOOL_STARTED),
        (3, ASSISTANT_DELTA),
        (4, TOOL_FINISHED),
        (5, ASSISTANT_DELTA),
        (6, RUN_COMPLETED),
        ]
    assert rows[1].payload == {"parts": [{"seq": 2, "text": "You spent "}, {"seq": 3, "text": "25000 "}]}


async def test_a_resumed_run_carries_on_numbering(seeded_run: SeededRun) -> None:

    """A new publisher for the same run starts after the last saved number."""

    await publish_turn(seeded_run.run_id)

    publisher = await RunPublisher(seeded_run.run_id).open()

    event = await publisher.emit(RunEvent(TOOL_STARTED, TOOL))

    assert event.seq == 7


async def test_an_ended_run_replays_steps_snapshot_and_end(seeded_run: SeededRun) -> None:

    """A listener with nothing seen gets each tool step, the whole reply as one snapshot, then the final event."""

    await publish_turn(seeded_run.run_id)
    await set_status(seeded_run.run_id, RunStatus.completed)

    assert await collect(seeded_run.run_id, 0) == [
        (1, TOOL_STARTED),
        (4, TOOL_FINISHED),
        (6, ASSISTANT_SNAPSHOT),
        (6, RUN_COMPLETED),
        ]


async def test_a_reconnect_gets_only_the_steps_it_missed(seeded_run: SeededRun) -> None:

    """A listener that saw up to event 3 gets only the later tool step, then the snapshot and the end."""

    await publish_turn(seeded_run.run_id)
    await set_status(seeded_run.run_id, RunStatus.completed)

    assert await collect(seeded_run.run_id, 3) == [
        (4, TOOL_FINISHED),
        (6, ASSISTANT_SNAPSHOT),
        (6, RUN_COMPLETED),
        ]


async def test_a_listener_follows_live_events_to_the_end(seeded_run: SeededRun) -> None:

    """A listener that joins a running run gets every event live, numbered in order, ending on completion."""

    await set_status(seeded_run.run_id, RunStatus.running)

    listener = asyncio.create_task(collect(seeded_run.run_id, 0))

    await asyncio.sleep(0.3)
    await publish_turn(seeded_run.run_id)

    events = await asyncio.wait_for(listener, timeout=10)

    assert [seq for seq, _ in events] == [1, 2, 3, 4, 5, 6]
    assert events[-1] == (6, RUN_COMPLETED)


async def test_old_events_of_ended_runs_are_deleted(seeded_run: SeededRun) -> None:

    """Cleanup deletes events past the keep window of an ended run, and keeps those of a run still active."""

    await publish_turn(seeded_run.run_id)

    async with SessionLocal() as session:

        await session.execute(
            update(RunEventRecord)
            .where(RunEventRecord.run_id == seeded_run.run_id)
            .values(created_at=func.now() - timedelta(days=2))
            )

        await session.commit()

    async with SessionLocal() as session:

        await RunEventRepository(session).delete_old(24)

        await session.commit()

    assert len(await saved_rows(seeded_run.run_id)) == 5

    await set_status(seeded_run.run_id, RunStatus.completed)

    async with SessionLocal() as session:

        await RunEventRepository(session).delete_old(24)

        await session.commit()

    assert await saved_rows(seeded_run.run_id) == []


async def test_a_saved_cancel_stops_the_next_call(seeded_run: SeededRun) -> None:

    """The check before a model or tool call passes for a running run and raises once a cancel is saved."""

    await set_status(seeded_run.run_id, RunStatus.running)

    await stop_if_cancelled(seeded_run.run_id)

    await set_status(seeded_run.run_id, RunStatus.cancel_requested)

    with pytest.raises(RunCancelled):
        await stop_if_cancelled(seeded_run.run_id)

    async with SessionLocal() as session:
        status = await session.scalar(select(AgentRun.status).where(AgentRun.id == seeded_run.run_id))

    assert status == RunStatus.cancel_requested
