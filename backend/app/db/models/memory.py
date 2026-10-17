"""The table models for long-term user memories and the history of every change to them."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import MemoryActorType, MemoryEventType, MemoryStatus
from app.db.models.base import created_at_column, db_enum, updated_at_column
from app.db.session import Base


class MemoryItem(Base):

    """One durable fact about a user that the structured financial tables do not already hold."""

    __tablename__ = "memory_items"

    __table_args__ = (
        Index("ix_memory_items_user_status", "user_id", "status"),
        Index(
            "uq_memory_items_one_active_key",
            "user_id",
            "namespace",
            "memory_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
            ),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    memory_type: Mapped[str] = mapped_column(Text, nullable=False)
    namespace: Mapped[str] = mapped_column(Text, nullable=False)
    memory_key: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[MemoryStatus] = mapped_column(
        db_enum(MemoryStatus, "memory_status"),
        nullable=False,
        server_default=MemoryStatus.active.value,
        )
    source_message_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("messages.id"))
    source_conversation_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("conversations.id"))
    source_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("agent_runs.id"))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class MemoryEvent(Base):

    """One history row saying how a memory was created, changed, confirmed, rejected or removed, and why."""

    __tablename__ = "memory_events"

    __table_args__ = (
        Index("ix_memory_events_memory_id", "memory_id"),
        Index("ix_memory_events_outbox_event_id", "outbox_event_id"),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    memory_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("memory_items.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    event_type: Mapped[MemoryEventType] = mapped_column(
        db_enum(MemoryEventType, "memory_event_type"),
        nullable=False,
        )
    old_content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_message_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("messages.id"))
    source_conversation_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("conversations.id"))
    source_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("agent_runs.id"))
    outbox_event_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("outbox_events.id"))
    actor_type: Mapped[MemoryActorType] = mapped_column(
        db_enum(MemoryActorType, "memory_actor_type"),
        nullable=False,
        )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
