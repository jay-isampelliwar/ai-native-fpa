"""Store the transcript of each conversation, which nothing durable held before this revision.

The checkpointer persisted graph state per thread and that was mistaken for history. It is not:
checkpoints are encrypted, shaped for resuming a paused run, and subject to their own retention. A
person who closed the tab lost every question they had asked. These two tables are the readable
record, written on every turn of both the streaming and non streaming endpoints.

``conversations.id`` is the conversation id the API already issues and LangGraph already uses as its
thread id, reused rather than reinvented. One string identifies the session everywhere, so a
transcript and the checkpoint that can resume it are joinable without a mapping table.

The message rows carry ``position`` and a unique constraint on it. Ordering by ``created_at`` looks
sufficient until a question and an immediate refusal land in the same millisecond and the transcript
renders the answer above the question.

Deleting a conversation cascades to its messages. This is the one place in the service where deletion
is offered at all - a chat a person chose to discard is theirs to discard - and it is deliberately
not offered for anything that constitutes a financial record or an audit trail.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:

    """Create the conversation and message tables, with the ordering guarantee the transcript needs."""

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(120), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index("ix_conversations_user_last_message", "conversations", ["user_id", "last_message_at"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(64),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("blocks", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("skill_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column("evidence_ids", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("calculator_versions", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_conversation_messages_user_id", "conversation_messages", ["user_id"])
    op.create_index(
        "ix_conversation_messages_conversation",
        "conversation_messages",
        ["conversation_id", "position"],
    )

    op.create_unique_constraint(
        "uq_conversation_messages_position",
        "conversation_messages",
        ["conversation_id", "position"],
    )

    op.create_check_constraint(
        "ck_conversation_messages_role",
        "conversation_messages",
        "role IN ('user','planner')",
    )


def downgrade() -> None:

    """Drop both tables, messages first so the foreign key does not block the parent."""

    op.drop_table("conversation_messages")

    op.drop_index("ix_conversations_user_last_message", table_name="conversations")
    op.drop_index("ix_conversations_user_id", table_name="conversations")

    op.drop_table("conversations")
