"""The shapes passed between the memory extractor, the repository and the worker."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.db.enums import MemoryStatus


@dataclass(frozen=True)
class MemoryCandidate:

    """One memory the extractor found in a chat, before it is saved."""

    memory_type: str
    namespace: str
    memory_key: str | None
    content: dict[str, Any]
    confidence: Decimal | None = None
    confirmed_by_user: bool = False
    status: MemoryStatus = MemoryStatus.active
    source_message_id: int | None = None


@dataclass(frozen=True)
class MemorySource:

    """Where a batch of memories came from: the user, chat, run and outbox event behind them."""

    user_id: int
    conversation_id: int
    run_id: int
    outbox_event_id: int
