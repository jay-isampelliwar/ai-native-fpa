"""The in-process channel that carries one run's events from its worker task to every listener."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.db.enums import RunStatus


ASSISTANT_SNAPSHOT = "assistant.snapshot"
ASSISTANT_DELTA = "assistant.delta"
TOOL_STARTED = "tool.started"
TOOL_FINISHED = "tool.finished"
RUN_COMPLETED = "run.completed"
RUN_FAILED = "run.failed"
RUN_CANCELLED = "run.cancelled"
APPROVAL_REQUIRED = "approval.required"

FINAL_EVENTS = {RUN_COMPLETED, RUN_FAILED, RUN_CANCELLED}

STREAM_END_EVENTS = FINAL_EVENTS | {APPROVAL_REQUIRED}

TOOL_EVENTS = {TOOL_STARTED, TOOL_FINISHED}

FINAL_EVENT_FOR_STATUS = {
    RunStatus.completed: RUN_COMPLETED,
    RunStatus.failed: RUN_FAILED,
    RunStatus.cancelled: RUN_CANCELLED,
    }


@dataclass(frozen=True)
class RunEvent:

    """One thing that happened in a run, with a name the frontend switches on and its data."""

    name: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:

        """Format the event as one server-sent event block."""

        return f"event: {self.name}\ndata: {json.dumps(self.data)}\n\n"


class RunEvents:

    """Keeps one queue per listener per run, copies every event into each, and remembers each live run's text and tool steps so far."""

    def __init__(self) -> None:

        """Start with no listeners, no live text and no live tool steps."""

        self.listeners: dict[int, set[asyncio.Queue[RunEvent]]] = {}
        self.texts: dict[int, str] = {}
        self.tools: dict[int, dict[str, RunEvent]] = {}

    def publish(self, run_id: int, event: RunEvent) -> None:

        """Update the run's text and tool steps so far, then hand the event to everyone listening, without waiting on any of them."""

        if event.name == ASSISTANT_DELTA:
            self.texts[run_id] = self.texts.get(run_id, "") + event.data["text"]

        if event.name in TOOL_EVENTS:
            self.tools.setdefault(run_id, {})[event.data["id"]] = event

        if event.name in FINAL_EVENTS:
            self.texts.pop(run_id, None)
            self.tools.pop(run_id, None)

        for queue in self.listeners.get(run_id, set()):
            queue.put_nowait(event)

    def subscribe(self, run_id: int) -> asyncio.Queue[RunEvent]:

        """Open an inbox for this run, seeded with each tool's latest step and the text so far, so a late listener misses nothing and sees nothing twice."""

        queue: asyncio.Queue[RunEvent] = asyncio.Queue()

        for tool_event in self.tools.get(run_id, {}).values():
            queue.put_nowait(tool_event)

        text_so_far = self.texts.get(run_id)

        if text_so_far:
            queue.put_nowait(RunEvent(ASSISTANT_SNAPSHOT, {"text": text_so_far}))

        self.listeners.setdefault(run_id, set()).add(queue)

        return queue

    async def drain(self, run_id: int, queue: asyncio.Queue[RunEvent]) -> AsyncIterator[RunEvent]:

        """Yield events from an open inbox, stop after the final one or a pause for approval, and always close the inbox."""

        try:

            while True:

                event = await queue.get()

                yield event

                if event.name in STREAM_END_EVENTS:
                    return

        finally:

            self.stop_listening(run_id, queue)

    async def listen(self, run_id: int) -> AsyncIterator[RunEvent]:

        """Subscribe and yield this run's events until the final one."""

        queue = self.subscribe(run_id)

        async for event in self.drain(run_id, queue):
            yield event

    def stop_listening(self, run_id: int, queue: asyncio.Queue[RunEvent]) -> None:

        """Remove one listener, and drop the run's entry once nobody is left."""

        queues = self.listeners.get(run_id)

        if queues is None:
            return

        queues.discard(queue)

        if not queues:
            del self.listeners[run_id]


run_events = RunEvents()
