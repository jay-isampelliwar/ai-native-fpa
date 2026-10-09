"""The status and role values stored in the conversation, message, run and tool call tables."""

from enum import StrEnum


class ConversationStatus(StrEnum):

    """Where a conversation is in its life."""

    active = "active"
    archived = "archived"
    deleted = "deleted"


class MessageRole(StrEnum):

    """Who wrote a message."""

    user = "user"
    assistant = "assistant"
    tool = "tool"
    system = "system"


class MessageStatus(StrEnum):

    """Whether a message is still being written or has ended."""

    streaming = "streaming"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class RunStatus(StrEnum):

    """Where one agent run is between queued and its final state."""

    queued = "queued"
    running = "running"
    cancel_requested = "cancel_requested"
    cancelled = "cancelled"
    completed = "completed"
    failed = "failed"


class ToolCallStatus(StrEnum):

    """Where one tool call is between requested and its final state."""

    requested = "requested"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    unknown = "unknown"


ACTIVE_RUN_STATUSES = (RunStatus.queued, RunStatus.running, RunStatus.cancel_requested)
