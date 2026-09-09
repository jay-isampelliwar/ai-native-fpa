"""Running work that outlives a request, without pretending it is part of the conversation.

Extracting a long statement takes longer than a user will hold a request open, and far longer than
any skill's time budget. It is not a graph run: nothing about it needs routing, permissions
re-checked per step, or a human in the middle. It is a job, and the graph has no concept of one -
so this module adds the smallest one that works.

Jobs are tracked in memory and run as asyncio tasks. That is honest about what it is: adequate for
one process, lost on restart, and replaceable by a real queue behind the same two functions. What
it must not become is a second place where records get written - a job here stages rows, and a
person still commits them.

Every job records its exception rather than letting it vanish. An asyncio task whose result is
never awaited swallows failures silently, which for a background extraction means a user watching
a spinner that will never finish.

``JobHandle`` is deliberately thin. Progress belongs in the database row the job is updating, not
in memory here, so a client polls the import's status and gets the same answer after a restart as
before one.

``wait`` polls ``task.done()`` rather than awaiting the task. A task belongs to the loop that
created it, and awaiting it from another one raises - which happens whenever the caller is not on
the loop that started the job, as under a test client or any thread based server. Polling a done
flag is safe from anywhere and costs a few milliseconds on a path only tests use.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

POLL_SECONDS = 0.02


@dataclass
class JobHandle:

    """One background job, kept only so a failure has somewhere to be recorded and seen."""

    job_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    task: asyncio.Task | None = None
    error: str | None = None


class JobRunner:

    """Starts background work and keeps enough of it to notice when something failed."""

    def __init__(self) -> None:

        """Start with no jobs, holding handles only for the life of the process."""

        self._jobs: dict[str, JobHandle] = {}

    def start(self, job_id: str, work: Callable[[], Awaitable[None]]) -> JobHandle:

        """Run one coroutine in the background, recording any exception it raises."""

        handle = JobHandle(job_id=job_id)

        async def run() -> None:

            try:
                await work()

            except Exception as exc:

                handle.error = f"{type(exc).__name__}: {exc}"

        handle.task = asyncio.create_task(run())

        self._jobs[job_id] = handle

        return handle

    def get(self, job_id: str) -> JobHandle | None:

        """Look up a job this process started, which is all this runner can know about."""

        return self._jobs.get(job_id)

    async def wait(self, job_id: str, timeout_seconds: float = 30.0) -> bool:

        """Wait for one job to finish by polling, which is safe from a different loop than started it."""

        handle = self._jobs.get(job_id)

        if handle is None or handle.task is None:
            return True

        waited = 0.0

        while not handle.task.done() and waited < timeout_seconds:

            await asyncio.sleep(POLL_SECONDS)

            waited += POLL_SECONDS

        return handle.task.done()


job_runner = JobRunner()
