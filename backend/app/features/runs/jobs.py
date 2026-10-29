"""The jobs that start or resume a run: sent to the Redis run stream for an agent worker, or run in this process when RUN_EXECUTION is inline."""

import asyncio
import logging
from collections.abc import Coroutine
from contextlib import suppress
from dataclasses import asdict, dataclass
from typing import Any

import orjson
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.redis import publish_event
from app.db.enums import RunStatus
from app.db.session import SessionLocal
from app.features.runs.registry import run_registry
from app.features.runs.repository import FINAL_RUN_STATUSES, RunRepository
from app.features.runs.worker import execute_run, resume_claimed, resume_run, start_claimed


log = logging.getLogger(__name__)

START = "start"
RESUME = "resume"

SETTLE_POLL_SECONDS = 0.25

SETTLED_STATUSES = (*FINAL_RUN_STATUSES, RunStatus.awaiting_approval)


@dataclass(frozen=True)
class RunJob:

    """Everything a worker needs to start or resume one run, with no extra reads."""

    kind: str
    run_id: int
    conversation_id: int
    user_id: int
    assistant_message_id: int
    user_text: str | None = None
    answer: dict[str, Any] | None = None
    final_status: str = RunStatus.completed.value

    def to_fields(self) -> dict[str, str]:

        """Encode the job as the flat string fields one Redis stream entry holds."""

        return {"kind": self.kind, "run_id": str(self.run_id), "job": orjson.dumps(asdict(self)).decode()}

    @classmethod
    def from_fields(cls, fields: dict[str, str]) -> "RunJob":

        """Decode a job read from the run stream."""

        return cls(**orjson.loads(fields["job"]))

    def work(self) -> Coroutine[Any, Any, None]:

        """The coroutine that takes the run for this process and drives it."""

        if self.kind == START:
            return execute_run(self.run_id, self.conversation_id, self.user_id, self.assistant_message_id, self.user_text)

        return resume_run(
            self.run_id,
            self.conversation_id,
            self.user_id,
            self.assistant_message_id,
            self.answer,
            RunStatus(self.final_status),
            )

    def claimed_work(self) -> Coroutine[Any, Any, None]:

        """The coroutine that drives the run once this worker has already taken it."""

        if self.kind == START:
            return start_claimed(self.run_id, self.conversation_id, self.user_id, self.assistant_message_id, self.user_text)

        return resume_claimed(
            self.run_id,
            self.conversation_id,
            self.user_id,
            self.assistant_message_id,
            self.answer,
            RunStatus(self.final_status),
            )


def queued_mode() -> bool:

    """Say whether runs go to agent workers through Redis rather than running in this process."""

    return get_settings().RUN_EXECUTION == "queue"


async def enqueue(job: RunJob) -> bool:

    """Put the job on the run stream and note the time it was sent, and say whether it was sent; the sweeps handle a failed send."""

    try:
        await publish_event(get_settings().REDIS_RUN_STREAM, job.to_fields())

    except RedisError:

        log.exception("could not send the %s job of run %s", job.kind, job.run_id)

        return False

    async with SessionLocal() as session:

        await RunRepository(session).mark_enqueued(job.run_id)

        await session.commit()

    return True


async def submit(job: RunJob) -> None:

    """Send the job to the agent workers, or start it as a task in this process when running inline."""

    if queued_mode():

        await enqueue(job)

        return

    run_registry.start(job.run_id, job.work())


async def wait_until_settled(run_id: int, timeout: float) -> RunStatus | None:

    """Poll the run's saved status until it has ended or paused again, or the timeout passes, and return the last status seen."""

    status = None

    with suppress(TimeoutError):

        async with asyncio.timeout(timeout):

            while True:

                async with SessionLocal() as session:
                    status = await RunRepository(session).get_status(run_id)

                if status is None or status in SETTLED_STATUSES:
                    return status

                await asyncio.sleep(SETTLE_POLL_SECONDS)

    log.warning("run %s did not settle within %s seconds, last seen %s", run_id, timeout, status)

    return status


async def run_and_wait(job: RunJob) -> None:

    """Run the job to its end before returning: in this process when inline, or through a worker and polling when queued."""

    if not queued_mode():

        await job.work()

        return

    await enqueue(job)

    await wait_until_settled(job.run_id, get_settings().TURN_TIMEOUT_SECONDS + get_settings().RUN_STALE_AFTER_SECONDS)

