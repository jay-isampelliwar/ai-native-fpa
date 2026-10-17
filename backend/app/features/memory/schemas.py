"""The shapes passed between the memory extractor, the repository and the worker."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.db.enums import MemoryStatus


class ExtractedMemory(BaseModel):

    """One memory exactly as the LLM proposed it, before the rules check it."""

    memory_type: str = Field(description="preference or episodic")
    namespace: str = Field(description="One of the allowed namespaces")
    memory_key: str = Field(description="Short snake_case key; reuse the existing key when updating a memory")
    content: dict[str, Any] = Field(description="The memory as a small JSON object, for example {\"sectors\": [\"tobacco\"]}")
    source_message_id: int = Field(description="The id of the user message that supports this memory")
    confidence: float = Field(description="0 to 1, how sure you are this is true and worth keeping")
    explicit: bool = Field(description="True only if the user said it directly, False if inferred")


class ExtractionResult(BaseModel):

    """Every memory the LLM found in one run, possibly none."""

    memories: list[ExtractedMemory] = Field(default_factory=list)


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
