"""The in-process map from run id to the asyncio task running it, so a cancel can find the task."""

import asyncio
import os
import socket
from collections.abc import Coroutine
from typing import Any


WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


class RunRegistry:

    """Holds every run task this process started, until the task ends."""

    def __init__(self) -> None:

        """Start with no running tasks."""

        self.tasks: dict[int, asyncio.Task] = {}

    def start(self, run_id: int, work: Coroutine[Any, Any, None]) -> asyncio.Task:

        """Run the work as a background task, remember it, and forget it once it ends."""

        task = asyncio.create_task(work, name=f"run-{run_id}")

        self.tasks[run_id] = task

        task.add_done_callback(lambda _: self.tasks.pop(run_id, None))

        return task

    def get(self, run_id: int) -> asyncio.Task | None:

        """Return the task for this run if this process is running it."""

        return self.tasks.get(run_id)

    def cancel(self, run_id: int) -> bool:

        """Cancel the run's task if this process is running it, and say whether it was found."""

        task = self.tasks.get(run_id)

        if task is None:
            return False

        task.cancel()

        return True


run_registry = RunRegistry()
