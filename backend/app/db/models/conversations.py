"""The table models for conversations, messages, agent runs and tool calls."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import ConversationStatus, MessageRole, MessageStatus, RunStatus, ToolCallStatus
from app.db.models.base import created_at_column, db_enum, updated_at_column
from app.db.session import Base


class Conversation(Base):

    """One chat thread that belongs to one user."""

    __tablename__ = "conversations"

    __table_args__ = (
        Index("ix_conversations_user_id", "user_id"),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ConversationStatus] = mapped_column(
        db_enum(ConversationStatus, "conversation_status"),
        nullable=False,
        server_default=ConversationStatus.active.value,
        )
    current_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    summary: Mapped[str | None] = mapped_column(Text)
    summarized_through_sequence: Mapped[int | None] = mapped_column(BigInteger, server_default="0")
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):

    """One user, assistant, tool or system message inside a conversation."""

    __tablename__ = "messages"

    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence_number", name="uq_messages_conversation_sequence"),
        Index("idx_messages_conversation_sequence", "conversation_id", "sequence_number"),
        Index("ix_messages_run_id", "run_id"),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conversations.id"),
        nullable=False,
        )
    run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("agent_runs.id", name="fk_messages_run_id"),
        )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[MessageRole] = mapped_column(db_enum(MessageRole, "message_role"), nullable=False)
    status: Mapped[MessageStatus] = mapped_column(db_enum(MessageStatus, "message_status"), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRun(Base):

    """One agent turn from queued to completed, cancelled or failed."""

    __tablename__ = "agent_runs"

    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "client_request_id",
            name="uq_agent_runs_conversation_client_request",
            ),
        Index("idx_agent_runs_conversation_created", "conversation_id", text("created_at DESC")),
        Index("idx_agent_runs_status", "status"),
        Index("idx_agent_runs_worker_status", "worker_id", "status"),
        Index(
            "idx_agent_runs_heartbeat",
            "heartbeat_at",
            postgresql_where=text("status IN ('running', 'cancel_requested')"),
            ),
        Index(
            "idx_agent_runs_queued_unsent",
            "created_at",
            postgresql_where=text("status = 'queued' AND enqueued_at IS NULL"),
            ),
        Index(
            "uq_agent_runs_one_active",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'cancel_requested', 'awaiting_approval')"),
            ),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conversations.id"),
        nullable=False,
        )
    client_request_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[RunStatus] = mapped_column(
        db_enum(RunStatus, "agent_run_status"),
        nullable=False,
        server_default=RunStatus.queued.value,
        )
    worker_id: Mapped[str | None] = mapped_column(String(255))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    model_calls: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))


class RunEventRecord(Base):

    """One saved event of a run, numbered in order, so a listener that reconnects can catch up."""

    __tablename__ = "run_events"

    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_run_events_run_seq"),
        Index("idx_run_events_created", "created_at"),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class ToolCall(Base):

    """One tool the model asked for during a run, with its arguments and result."""

    __tablename__ = "tool_calls"

    __table_args__ = (
        UniqueConstraint("conversation_id", "tool_call_id", name="uq_tool_calls_conversation_tool_call"),
        Index("ix_tool_calls_message_id", "message_id"),
        Index("ix_tool_calls_run_id", "run_id"),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conversations.id"),
        nullable=False,
        )
    message_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("messages.id"),
        nullable=False,
        )
    run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("agent_runs.id", name="fk_tool_calls_run_id"),
        )
    tool_call_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[ToolCallStatus] = mapped_column(
        db_enum(ToolCallStatus, "tool_call_status"),
        nullable=False,
        server_default=ToolCallStatus.requested.value,
        )
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
