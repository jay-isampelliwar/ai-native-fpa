"""The table model for outbox events waiting to be published to Redis."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import OutboxEventType, OutboxStatus
from app.db.models.base import created_at_column, db_enum
from app.db.session import Base


class OutboxEvent(Base):

    """One event saved in the same commit as its cause, then published to Redis by the outbox publisher."""

    __tablename__ = "outbox_events"

    __table_args__ = (
        UniqueConstraint(
            "event_type",
            "aggregate_type",
            "aggregate_id",
            name="uq_outbox_events_event_aggregate",
            ),
        Index("idx_outbox_events_status_available", "status", "available_at"),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_type: Mapped[OutboxEventType] = mapped_column(
        db_enum(OutboxEventType, "outbox_event_type"),
        nullable=False,
        )
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[int | None] = mapped_column(BigInteger)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        db_enum(OutboxStatus, "outbox_status"),
        nullable=False,
        server_default=OutboxStatus.pending.value,
        )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(255))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
