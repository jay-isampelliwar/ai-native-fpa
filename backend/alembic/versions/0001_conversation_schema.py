"""Create the conversation, message and tool call tables of the fresh schema.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

CONVERSATION_STATUS = postgresql.ENUM(
    "active",
    "archived",
    "deleted",
    name="conversation_status",
    create_type=False,
)

MESSAGE_ROLE = postgresql.ENUM(
    "user",
    "assistant",
    "tool",
    "system",
    name="message_role",
    create_type=False,
)

MESSAGE_STATUS = postgresql.ENUM(
    "streaming",
    "completed",
    "cancelled",
    "failed",
    name="message_status",
    create_type=False,
)

TOOL_CALL_STATUS = postgresql.ENUM(
    "requested",
    "running",
    "completed",
    "failed",
    name="tool_call_status",
    create_type=False,
)

ENUM_TYPES = (CONVERSATION_STATUS, MESSAGE_ROLE, MESSAGE_STATUS, TOOL_CALL_STATUS)


def upgrade() -> None:

    """Create the four enum types, then the three tables and the indexes their reads need."""

    bind = op.get_bind()

    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=False)

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("status", CONVERSATION_STATUS, nullable=False, server_default="active"),
        sa.Column("current_sequence", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summarized_through_sequence", sa.BigInteger(), nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("role", MESSAGE_ROLE, nullable=False),
        sa.Column("status", MESSAGE_STATUS, nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("conversation_id", "sequence_number", name="uq_messages_conversation_sequence"),
    )

    op.create_index("idx_messages_conversation_sequence", "messages", ["conversation_id", "sequence_number"])

    op.create_table(
        "tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id"),
            nullable=False,
        ),
        sa.Column("tool_call_id", sa.String(255), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("status", TOOL_CALL_STATUS, nullable=False, server_default="requested"),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("conversation_id", "tool_call_id", name="uq_tool_calls_conversation_tool_call"),
    )

    op.create_index("ix_tool_calls_message_id", "tool_calls", ["message_id"])


def downgrade() -> None:

    """Drop the three tables children first, then the enum types nothing references any more."""

    op.drop_table("tool_calls")
    op.drop_table("messages")
    op.drop_table("conversations")

    bind = op.get_bind()

    for enum_type in reversed(ENUM_TYPES):
        enum_type.drop(bind, checkfirst=False)
