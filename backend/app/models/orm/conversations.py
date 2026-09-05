"""Tables holding the transcript of a conversation, which the checkpointer deliberately does not.

A LangGraph checkpoint already persists something per thread, and it is tempting to call that the
history. It is not. A checkpoint is the machine state of the most recent run - encrypted, versioned,
pruned, and shaped for resuming a paused graph rather than for reading. Asking it "what did this
person ask me last Tuesday" means decrypting blobs and reconstructing objects, and the answer would
still be only as complete as the retention policy on the checkpoint tables. These two tables are the
readable record instead, and they are ordinary rows anyone can query.

``ConversationRow`` exists so a session is a thing rather than an inference from a group of messages.
It carries the counters a list needs - when it was last spoken to, how many turns it holds - because
computing those with an aggregate over every message of every conversation is the query that gets
slow first, and it is on the screen a person sees at startup.

``title`` is the first thing the user said, truncated. It is stored rather than derived so that
renaming a conversation later is an update rather than a schema change, and so a list can be rendered
without loading a message from each conversation to find out what it was about.

``position`` orders the turns rather than ``created_at``. Two rows written inside the same millisecond
- a question and the answer to a refusal, which is exactly what a fast path produces - would sort
arbitrarily by timestamp, and a transcript that occasionally shows the answer above the question is
worse than useless. The unique constraint on ``(conversation_id, position)`` is what makes the
ordering a guarantee rather than a hope.

``blocks`` stores what the client was actually shown, not a re-render of it. A skill built those
blocks from figures computed at the time, and re-deriving them on read would quietly answer a
question about last month with this month's records. History has to be what happened.

The message table repeats ``user_id`` alongside the foreign key to its conversation. That is denormal
on purpose: every read is ownership scoped, and an index on the message table's own owner column
means the common query never has to join to find out whether the caller is allowed to see the row.
"""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecordId

MESSAGE_ROLES = ("user", "planner")

TITLE_LENGTH = 120


class ConversationRow(Base):

    """One chat session, identified by the same string that is the graph's thread id."""

    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_last_message", "user_id", "last_message_at"),)

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    title: Mapped[str | None] = mapped_column(String(TITLE_LENGTH))
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class ConversationMessageRow(Base):

    """One turn of a conversation, stored as the client was shown it rather than as state to replay."""

    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "position", name="uq_conversation_messages_position"),
        Index("ix_conversation_messages_conversation", "conversation_id", "position"),
    )

    id: Mapped[RecordId]
    conversation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    blocks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    skill_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(Text)

    evidence_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    calculator_versions: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
