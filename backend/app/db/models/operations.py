"""The table model for the saved result of each write tool call."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import created_at_column
from app.db.session import Base


class ToolOperation(Base):

    """One write tool call that committed, with its result, saved in the same commit as the write itself."""

    __tablename__ = "tool_operations"

    __table_args__ = (
        UniqueConstraint("conversation_id", "tool_call_id", name="uq_tool_operations_conversation_tool_call"),
        Index("ix_tool_operations_user_id", "user_id"),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversations.id"), nullable=False)
    run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("agent_runs.id"))
    tool_call_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
