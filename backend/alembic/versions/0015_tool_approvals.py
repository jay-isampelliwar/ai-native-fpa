"""Add tool_approvals and the awaiting_approval run and tool call states for actions the user must approve first."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

APPROVAL_STATUS = postgresql.ENUM(
    "pending",
    "approved",
    "rejected",
    "expired",
    "cancelled",
    name="approval_status",
    create_type=False,
)

OLD_RUN_STATUSES = ("queued", "running", "cancel_requested", "cancelled", "completed", "failed")

OLD_ACTIVE_RUN_STATUSES = ("queued", "running", "cancel_requested")

NEW_ACTIVE_RUN_STATUSES = (*OLD_ACTIVE_RUN_STATUSES, "awaiting_approval")

OLD_TOOL_CALL_STATUSES = ("requested", "running", "completed", "failed", "cancelled", "unknown")

NEW_TOOL_CALL_STATUSES = ("awaiting_approval", "rejected")


def quoted(values: tuple[str, ...]) -> str:

    """Join status values into a quoted, comma separated SQL list."""

    return ", ".join(f"'{value}'" for value in values)


def create_one_active_index(statuses: tuple[str, ...]) -> None:

    """Allow at most one run in the given active statuses per conversation."""

    op.create_index(
        "uq_agent_runs_one_active",
        "agent_runs",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({quoted(statuses)})"),
    )


def shrink_enum(table: str, type_name: str, values: tuple[str, ...], default: str) -> None:

    """Rebuild a Postgres enum type with only the given values, since Postgres cannot drop one value."""

    op.execute(f"ALTER TABLE {table} ALTER COLUMN status DROP DEFAULT")
    op.execute(f"ALTER TYPE {type_name} RENAME TO {type_name}_old")
    op.execute(f"CREATE TYPE {type_name} AS ENUM ({quoted(values)})")
    op.execute(
        f"ALTER TABLE {table} ALTER COLUMN status TYPE {type_name} "
        f"USING status::text::{type_name}"
    )
    op.execute(f"ALTER TABLE {table} ALTER COLUMN status SET DEFAULT '{default}'")
    op.execute(f"DROP TYPE {type_name}_old")


def upgrade() -> None:

    """Add the new enum values in their own commit, widen the one active run index, then create tool_approvals."""

    with op.get_context().autocommit_block():

        op.execute("ALTER TYPE agent_run_status ADD VALUE IF NOT EXISTS 'awaiting_approval'")

        for status in NEW_TOOL_CALL_STATUSES:
            op.execute(f"ALTER TYPE tool_call_status ADD VALUE IF NOT EXISTS '{status}'")

    op.drop_index("uq_agent_runs_one_active", table_name="agent_runs")

    create_one_active_index(NEW_ACTIVE_RUN_STATUSES)

    APPROVAL_STATUS.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "tool_approvals",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("run_id", sa.BigInteger(), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("tool_call_id", sa.BigInteger(), sa.ForeignKey("tool_calls.id"), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("preview", postgresql.JSONB(), nullable=False),
        sa.Column("status", APPROVAL_STATUS, nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_tool_approvals_user_status", "tool_approvals", ["user_id", "status"])
    op.create_index("ix_tool_approvals_run_id", "tool_approvals", ["run_id"])
    op.create_index("ix_tool_approvals_status_expires", "tool_approvals", ["status", "expires_at"])
    op.create_index(
        "uq_tool_approvals_one_pending_call",
        "tool_approvals",
        ["tool_call_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:

    """Drop tool_approvals, end any paused runs and calls as cancelled, then shrink both enums back."""

    op.drop_index("uq_tool_approvals_one_pending_call", table_name="tool_approvals")
    op.drop_index("ix_tool_approvals_status_expires", table_name="tool_approvals")
    op.drop_index("ix_tool_approvals_run_id", table_name="tool_approvals")
    op.drop_index("ix_tool_approvals_user_status", table_name="tool_approvals")
    op.drop_table("tool_approvals")

    APPROVAL_STATUS.drop(op.get_bind(), checkfirst=False)

    op.execute(
        f"UPDATE tool_calls SET status = 'cancelled' WHERE status IN ({quoted(NEW_TOOL_CALL_STATUSES)})"
    )
    shrink_enum("tool_calls", "tool_call_status", OLD_TOOL_CALL_STATUSES, "requested")

    op.execute("UPDATE agent_runs SET status = 'cancelled' WHERE status = 'awaiting_approval'")
    op.drop_index("uq_agent_runs_one_active", table_name="agent_runs")
    shrink_enum("agent_runs", "agent_run_status", OLD_RUN_STATUSES, "queued")
    create_one_active_index(OLD_ACTIVE_RUN_STATUSES)
