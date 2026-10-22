"""Add tool_operations: the saved result of every write tool call, committed with the write, so a replayed call never writes twice."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:

    """Create tool_operations, unique on the conversation and the model's tool call id."""

    op.create_table(
        "tool_operations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("run_id", sa.BigInteger(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("tool_call_id", sa.String(255), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "conversation_id",
            "tool_call_id",
            name="uq_tool_operations_conversation_tool_call",
        ),
    )

    op.create_index("ix_tool_operations_user_id", "tool_operations", ["user_id"])


def downgrade() -> None:

    """Drop tool_operations."""

    op.drop_index("ix_tool_operations_user_id", table_name="tool_operations")
    op.drop_table("tool_operations")
