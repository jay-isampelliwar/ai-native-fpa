"""The events of one run, their names, and the Redis channels that carry them and cancel requests between processes."""

import json
from dataclasses import dataclass, field
from typing import Any

import orjson

from app.core.config import get_settings
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

FINAL_EVENT_FOR_STATUS = {
    RunStatus.completed: RUN_COMPLETED,
    RunStatus.failed: RUN_FAILED,
    RunStatus.cancelled: RUN_CANCELLED,
    }


@dataclass(frozen=True)
class RunEvent:

    """One thing that happened in a run, with a name the frontend switches on, its data, and its number once saved."""

    name: str
    data: dict[str, Any] = field(default_factory=dict)
    seq: int | None = None

    def to_sse(self) -> str:

        """Format the event as one server-sent event block, with its number as the id when it has one."""

        event_id = f"id: {self.seq}\n" if self.seq is not None else ""

        return f"{event_id}event: {self.name}\ndata: {json.dumps(self.data)}\n\n"

    def to_wire(self) -> str:

        """Encode the event for a Redis channel."""

        return orjson.dumps({"seq": self.seq, "name": self.name, "data": self.data}).decode()

    @classmethod
    def from_wire(cls, text: str) -> "RunEvent":

        """Decode an event read from a Redis channel."""

        fields = orjson.loads(text)

        return cls(fields["name"], fields["data"], fields["seq"])


def events_channel(run_id: int) -> str:

    """Name the Redis channel that carries one run's live events."""

    return f"{get_settings().REDIS_RUN_CHANNEL_PREFIX}:{run_id}:events"


def cancel_channel(run_id: int) -> str:

    """Name the Redis channel that asks whoever runs this run to stop it."""

    return f"{get_settings().REDIS_RUN_CHANNEL_PREFIX}:{run_id}:cancel"


def cancel_pattern() -> str:

    """The pattern that matches the cancel channel of every run."""

    return f"{get_settings().REDIS_RUN_CHANNEL_PREFIX}:*:cancel"


def run_id_from_channel(channel: str) -> int:

    """Read the run id back out of an events or cancel channel name."""

    return int(channel.rsplit(":", 2)[-2])
