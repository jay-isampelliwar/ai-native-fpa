"""The table models for conversations, messages, agent runs and tool calls."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import ConversationStatus, MessageRole, MessageStatus, RunStatus, ToolCallStatus
from app.db.session import Base


def db_enum(enum_class: type[StrEnum], name: str) -> ENUM:

    """Map a Python enum onto a Postgres enum type the migrations already created."""

    return ENUM(
        enum_class,
        name=name,
        create_type=False,
        values_callable=lambda members: [member.value for member in members],
        )


def created_at_column() -> Mapped[datetime]:

    """A timestamp the database fills in when the row is inserted."""

    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def updated_at_column() -> Mapped[datetime]:

    """A timestamp the database fills in on insert and the app refreshes on every update."""

    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        )


class Conversation(Base):

    """One chat thread that belongs to one user."""

    __tablename__ = "conversations"

    __table_args__ = (
        Index("ix_conversations_user_id", "user_id"),
        )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
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


class Message(Base):

    """One user, assistant, tool or system message inside a conversation."""

    __tablename__ = "messages"

    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence_number", name="uq_messages_conversation_sequence"),
        Index("idx_messages_conversation_sequence", "conversation_id", "sequence_number"),
        Index("ix_messages_run_id", "run_id"),
        )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id"),
        nullable=False,
        )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
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
            "uq_agent_runs_one_active",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'cancel_requested')"),
            ),
        )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
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
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ToolCall(Base):

    """One tool the model asked for during a run, with its arguments and result."""

    __tablename__ = "tool_calls"

    __table_args__ = (
        UniqueConstraint("conversation_id", "tool_call_id", name="uq_tool_calls_conversation_tool_call"),
        Index("ix_tool_calls_message_id", "message_id"),
        Index("ix_tool_calls_run_id", "run_id"),
        )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id"),
        nullable=False,
        )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id"),
        nullable=False,
        )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
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
