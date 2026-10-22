"""The table model for tool calls that wait for the user's approval before they run."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import ApprovalStatus
from app.db.models.base import created_at_column, db_enum, updated_at_column
from app.db.session import Base


class ToolApproval(Base):

    """One risky tool call paused for the user, with the exact arguments and preview they were shown."""

    __tablename__ = "tool_approvals"

    __table_args__ = (
        Index("ix_tool_approvals_user_status", "user_id", "status"),
        Index("ix_tool_approvals_run_id", "run_id"),
        Index("ix_tool_approvals_status_expires", "status", "expires_at"),
        Index(
            "uq_tool_approvals_one_pending_call",
            "tool_call_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            ),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversations.id"), nullable=False)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("agent_runs.id"), nullable=False)
    tool_call_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tool_calls.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    preview: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        db_enum(ApprovalStatus, "approval_status"),
        nullable=False,
        server_default=ApprovalStatus.pending.value,
        )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
