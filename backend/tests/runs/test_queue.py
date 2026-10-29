"""Tests that run jobs are sent, taken once, counted, and that runs with a stale worker fail, on real Postgres and Redis."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.redis import ensure_group, get_redis
from app.db.enums import RunStatus
from app.db.models import AgentRun, RunEventRecord
from app.db.session import SessionLocal
from app.features.runs import consumer
from app.features.runs.jobs import RESUME, START, RunJob, enqueue
from app.features.runs.repository import RunRepository
from app.features.runs.worker import claim_run
from tests.support import SeededRun


GROUP = "agent-workers-test"


def start_job(seeded: SeededRun) -> RunJob:

    """The start job of the seeded run."""

    return RunJob(START, seeded.run_id, seeded.conversation_id, seeded.user_id, seeded.assistant_message_id, user_text="hi")


async def load_run(run_id: int) -> AgentRun:

    """Return the run as saved now."""

    async with SessionLocal() as session:
        return await session.scalar(select(AgentRun).where(AgentRun.id == run_id))


async def set_run(run_id: int, **values) -> None:

    """Overwrite columns of the run."""

    async with SessionLocal() as session:

        await session.execute(update(AgentRun).where(AgentRun.id == run_id).values(**values))

        await session.commit()


def test_job_survives_the_stream_encoding() -> None:

    """A resume job read back from its stream fields equals the one sent."""

    job = RunJob(RESUME, 1, 2, 3, 4, answer={"decision": "approve"}, final_status=RunStatus.cancelled.value)

    assert RunJob.from_fields(job.to_fields()) == job


async def test_enqueue_sends_the_job_and_notes_the_time(
    seeded_run: SeededRun,
    redis_stream: str,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """Enqueue adds one entry with the job to the run stream and sets enqueued_at."""

    monkeypatch.setattr(get_settings(), "REDIS_RUN_STREAM", redis_stream)

    assert await enqueue(start_job(seeded_run))

    entries = await get_redis().xrange(redis_stream)

    assert len(entries) == 1
    assert RunJob.from_fields(entries[0][1]) == start_job(seeded_run)
    assert (await load_run(seeded_run.run_id)).enqueued_at is not None


async def test_a_queued_run_is_taken_once(seeded_run: SeededRun) -> None:

    """The first start claim moves the run to running with an owner and a heartbeat, and a second claim gets nothing."""

    assert await claim_run(seeded_run.run_id, starting=True)
    assert not await claim_run(seeded_run.run_id, starting=True)

    run = await load_run(seeded_run.run_id)

    assert run.status == RunStatus.running
    assert run.worker_id is not None
    assert run.heartbeat_at is not None


async def test_a_resume_needs_a_released_run(seeded_run: SeededRun) -> None:

    """A resume claim fails while another worker owns the run, and succeeds once the run is released."""

    await set_run(seeded_run.run_id, status=RunStatus.running, worker_id="other:1")

    assert not await claim_run(seeded_run.run_id, starting=False)

    async with SessionLocal() as session:

        await RunRepository(session).prepare_resume(seeded_run.run_id)

        await session.commit()

    assert await claim_run(seeded_run.run_id, starting=False)


async def fail_stale() -> list[int]:

    """Fail runs whose heartbeat is over an hour old, and return their ids."""

    async with SessionLocal() as session:

        failed = await RunRepository(session).fail_stale_runs(3600)

        await session.commit()

    return failed


async def test_stale_heartbeat_fails_the_run(seeded_run: SeededRun) -> None:

    """A running run whose worker stopped beating over an hour ago is failed as worker_lost, and a fresh one is left alone."""

    await set_run(seeded_run.run_id, status=RunStatus.running, worker_id="dead:1", heartbeat_at=func.now())

    assert seeded_run.run_id not in await fail_stale()

    await set_run(seeded_run.run_id, heartbeat_at=func.now() - timedelta(hours=2))

    assert seeded_run.run_id in await fail_stale()

    run = await load_run(seeded_run.run_id)

    assert run.status == RunStatus.failed
    assert run.failure_code == "worker_lost"


async def entry_for(stream: str, job: RunJob) -> tuple[str, dict[str, str]]:

    """Send the job, read it as the test consumer, and return the entry."""

    await ensure_group(stream, GROUP)
    await get_redis().xadd(stream, job.to_fields())

    entries = await get_redis().xreadgroup(GROUP, "test", {stream: ">"}, count=1)

    return entries[0][1][0]


async def pending_count(stream: str) -> int:

    """Return how many entries the test group has not acknowledged."""

    return (await get_redis().xpending(stream, GROUP))["pending"]


async def test_a_job_for_a_taken_run_is_skipped(seeded_run: SeededRun, redis_stream: str) -> None:

    """A second delivery of a start job for a run already running is acknowledged and not run again."""

    await set_run(seeded_run.run_id, status=RunStatus.running, worker_id="other:1")

    entry_id, fields = await entry_for(redis_stream, start_job(seeded_run))

    await consumer.handle_entry(redis_stream, GROUP, entry_id, fields)

    run = await load_run(seeded_run.run_id)

    assert await pending_count(redis_stream) == 0
    assert run.worker_id == "other:1"
    assert run.attempts == 1


async def test_too_many_deliveries_fail_the_run(seeded_run: SeededRun, redis_stream: str) -> None:

    """A job delivered more times than allowed fails its run, tells listeners, and is acknowledged."""

    await set_run(seeded_run.run_id, attempts=get_settings().RUN_MAX_ATTEMPTS)

    entry_id, fields = await entry_for(redis_stream, start_job(seeded_run))

    await consumer.handle_entry(redis_stream, GROUP, entry_id, fields)

    run = await load_run(seeded_run.run_id)

    async with SessionLocal() as session:
        events = list(await session.scalars(select(RunEventRecord.event_type).where(RunEventRecord.run_id == seeded_run.run_id)))

    assert await pending_count(redis_stream) == 0
    assert run.status == RunStatus.failed
    assert run.failure_code == "too_many_attempts"
    assert events == ["run.failed"]


async def test_an_unreadable_job_goes_to_the_dead_stream(redis_stream: str) -> None:

    """A stream entry that is not a job is moved to the dead stream and acknowledged."""

    await ensure_group(redis_stream, GROUP)
    await get_redis().xadd(redis_stream, {"job": "not json"})

    entries = await get_redis().xreadgroup(GROUP, "test", {redis_stream: ">"}, count=1)
    entry_id, fields = entries[0][1][0]

    await consumer.handle_entry(redis_stream, GROUP, entry_id, fields)

    assert await pending_count(redis_stream) == 0
    assert len(await get_redis().xrange(f"{redis_stream}:dead")) == 1
