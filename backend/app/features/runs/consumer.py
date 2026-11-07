"""The agent worker: a process that takes run jobs from the Redis run stream, drives them, stops them on request, and runs the sweeps."""

import asyncio
import logging
import signal
from contextlib import suppress

from redis.exceptions import RedisError

from app.agent import graph as planner
from app.agent.checkpointer import open_checkpointer
from app.core.config import get_settings
from app.core.redis import (
    ack,
    claim_stale,
    close_redis,
    ensure_group,
    get_redis,
    prune_consumers,
    publish_event,
    read_group,
    )
from app.db.models import AgentRun
from app.db.session import SessionLocal, engine
from app.features.approvals.sweeper import expire_due
from app.features.runs.events import RUN_FAILED, RunEvent, cancel_pattern, run_id_from_channel
from app.features.runs.jobs import START, RunJob, enqueue
from app.features.runs.publisher import record_event
from app.features.runs.registry import WORKER_ID, run_registry
from app.features.runs.repository import RunEventRepository, RunRepository
from app.features.runs.worker import FAILED_TEXT, claim_run
from app.observability.langfuse import shutdown_langfuse, start_langfuse


log = logging.getLogger(__name__)

BLOCK_MS = 5000

ERROR_SLEEP_SECONDS = 1.0

CANCEL_POLL_SECONDS = 1.0

SWEEP_INTERVAL_SECONDS = 30

RESEND_BATCH_SIZE = 50


def dead_stream(stream: str) -> str:

    """Name the stream where run jobs that could not be read are kept."""

    return f"{stream}:dead"


async def announce_failed(run_ids: list[int]) -> None:

    """Send run.failed to anyone listening on runs a sweep failed outside their task."""

    for run_id in run_ids:
        await record_event(run_id, RunEvent(RUN_FAILED, {"message": FAILED_TEXT}))


async def fail_run(run_id: int, failure_code: str) -> None:

    """Fail one run outside its task and tell its listeners."""

    async with SessionLocal() as session:

        run_ids = await RunRepository(session).fail_active_runs(failure_code, AgentRun.id == run_id)

        await session.commit()

    await announce_failed(run_ids)


async def count_attempt(run_id: int) -> int | None:

    """Count one more delivery of the run's job to a worker and return the new count."""

    async with SessionLocal() as session:

        attempts = await RunRepository(session).add_attempt(run_id)

        await session.commit()

    return attempts


async def drive(task: asyncio.Task) -> None:

    """Wait for a run task to end, however it ended, without taking its cancellation as this task's own."""

    await asyncio.wait([task])

    if not task.cancelled() and task.exception() is not None:
        log.error("run task %s ended with an error", task.get_name(), exc_info=task.exception())


async def handle_entry(
    stream: str,
    group: str,
    entry_id: str,
    fields: dict[str, str],
    ) -> None:

    """Count the delivery, take the run in Postgres, acknowledge the entry, then drive the run to its end or pause."""

    try:
        job = RunJob.from_fields(fields)

    except Exception:

        log.exception("run job %s could not be read, moving it to %s", entry_id, dead_stream(stream))

        await publish_event(dead_stream(stream), {**fields, "source_entry_id": entry_id})
        await ack(stream, group, entry_id)

        return

    attempts = await count_attempt(job.run_id)

    if attempts is not None and attempts > get_settings().RUN_MAX_ATTEMPTS:

        log.error("run %s was delivered %s times, failing it", job.run_id, attempts)

        await fail_run(job.run_id, "too_many_attempts")
        await ack(stream, group, entry_id)

        return

    claimed = attempts is not None and await claim_run(job.run_id, starting=job.kind == START)

    await ack(stream, group, entry_id)

    if not claimed:

        log.info("run %s %s job skipped, the run is not waiting for a worker", job.run_id, job.kind)

        return

    await drive(run_registry.start(job.run_id, job.claimed_work()))


async def next_entry(
    stream: str,
    group: str,
    consumer: str,
    ) -> tuple[str, dict[str, str]] | None:

    """Take one entry a dead worker left unacknowledged, or else wait for one new entry."""

    claim_idle_ms = get_settings().RUN_CLAIM_AFTER_SECONDS * 1000

    entries = await claim_stale(stream, group, consumer, claim_idle_ms, 1)

    if not entries:
        entries = await read_group(stream, group, consumer, 1, BLOCK_MS)

    return entries[0] if entries else None


async def consume(
    stream: str,
    group: str,
    consumer: str,
    ) -> None:

    """Read jobs while a slot is free, driving each in its own task, up to RUN_WORKER_CONCURRENCY at once, until cancelled."""

    slots = asyncio.Semaphore(get_settings().RUN_WORKER_CONCURRENCY)
    tasks: set[asyncio.Task] = set()

    async def handle_in_slot(entry_id: str, fields: dict[str, str]) -> None:

        """Handle one entry and free its slot after."""

        try:
            await handle_entry(stream, group, entry_id, fields)

        except Exception:
            log.exception("run job %s failed before its run started", entry_id)

        finally:
            slots.release()

    try:

        while True:

            await slots.acquire()

            try:
                entry = await next_entry(stream, group, consumer)

            except Exception:

                slots.release()

                log.exception("agent worker could not read the run stream")

                await asyncio.sleep(ERROR_SLEEP_SECONDS)

                continue

            if entry is None:

                slots.release()

                continue

            task = asyncio.create_task(handle_in_slot(*entry), name=f"job-{entry[0]}")

            tasks.add(task)
            task.add_done_callback(tasks.discard)

    finally:

        running = list(run_registry.tasks.values())

        for task in running:
            task.cancel()

        await asyncio.gather(*running, return_exceptions=True)

        for task in list(tasks):
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)


async def listen_for_cancels() -> None:

    """Cancel the local task of any run whose cancel channel gets a message, until cancelled."""

    while True:

        pubsub = get_redis().pubsub()

        try:

            await pubsub.psubscribe(cancel_pattern())

            while True:

                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=CANCEL_POLL_SECONDS)

                if message is not None:
                    run_registry.cancel(run_id_from_channel(message["channel"]))

        except (RedisError, OSError):

            log.exception("cancel listener lost Redis, reconnecting")

            await asyncio.sleep(ERROR_SLEEP_SECONDS)

        finally:
            await pubsub.aclose()


async def resend_unsent() -> int:

    """Send again the start job of every queued run whose first send never reached the queue, and return how many."""

    async with SessionLocal() as session:

        repo = RunRepository(session)

        jobs = []

        for run in await repo.unsent_queued_runs(get_settings().RUN_RESEND_AFTER_SECONDS, RESEND_BATCH_SIZE):

            user_message = await repo.get_user_message(run.id)
            assistant_message = await repo.get_assistant_message(run.id)
            user_id = await repo.get_owner_id(run.conversation_id)

            if user_message is None or assistant_message is None or user_id is None:
                continue

            text = user_message.content.get("text", "")

            jobs.append(RunJob(START, run.id, run.conversation_id, user_id, assistant_message.id, user_text=text))

    for job in jobs:
        await enqueue(job)

    return len(jobs)


async def sweep_once() -> None:

    """Fail runs with a stale heartbeat, resend unsent jobs, expire overdue approvals and delete old run events."""

    settings = get_settings()

    # TODO(idempotency): resuming stale runs from the checkpoint instead is safe; write tools replay from tool_operations.
    async with SessionLocal() as session:

        failed = await RunRepository(session).fail_stale_runs(settings.RUN_STALE_AFTER_SECONDS)

        await session.commit()

    if failed:

        log.warning("failed %s runs whose worker stopped: %s", len(failed), failed)

        await announce_failed(failed)

    resent = await resend_unsent()

    if resent:
        log.warning("sent again %s run jobs that never reached the queue", resent)

    expired = await expire_due()

    if expired:
        log.info("expired %s approvals", expired)

    async with SessionLocal() as session:

        deleted = await RunEventRepository(session).delete_old(settings.RUN_EVENTS_KEEP_HOURS)

        await session.commit()

    if deleted:
        log.info("deleted %s old run events", deleted)


async def sweep_forever() -> None:

    """Run the sweeps at startup and then on a fixed interval, until cancelled."""

    while True:

        try:
            await sweep_once()

        except Exception:
            log.exception("agent worker sweep failed")

        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)


async def start(stream: str, group: str) -> None:

    """Create the consumer group and delete old idle consumers, retrying until Redis is reachable."""

    while True:

        try:

            await ensure_group(stream, group)

            pruned = await prune_consumers(stream, group, WORKER_ID, get_settings().REDIS_CONSUMER_PRUNE_AFTER_SECONDS * 1000)

            if pruned:
                log.info("agent worker deleted idle consumers %s", pruned)

            return

        except Exception:

            log.exception("agent worker could not reach Redis, retrying")

            await asyncio.sleep(ERROR_SLEEP_SECONDS)


async def run_forever() -> None:

    """Compile the graph, then consume jobs, listen for cancels and sweep until stopped, and close every pool on exit."""

    settings = get_settings()
    stream = settings.REDIS_RUN_STREAM
    group = settings.REDIS_RUN_CONSUMER_GROUP

    start_langfuse(settings)

    try:

        async with open_checkpointer() as checkpointer:

            planner.planner_graph = planner.build_planner_graph(checkpointer)

            await start(stream, group)

            log.info("agent worker %s started on %s", WORKER_ID, stream)

            helpers = [
                asyncio.create_task(listen_for_cancels(), name="cancel-listener"),
                asyncio.create_task(sweep_forever(), name="run-sweeps"),
                ]

            try:
                await consume(stream, group, WORKER_ID)

            finally:

                for task in helpers:
                    task.cancel()

                await asyncio.gather(*helpers, return_exceptions=True)

    finally:

        shutdown_langfuse(get_settings())

        await close_redis()
        await engine.dispose()

        log.info("agent worker stopped")


async def main() -> None:

    """Run the worker, stopping it the same way on SIGTERM as on Ctrl+C."""

    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, asyncio.current_task().cancel)

    with suppress(asyncio.CancelledError):
        await run_forever()


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    with suppress(KeyboardInterrupt):
        asyncio.run(main())
