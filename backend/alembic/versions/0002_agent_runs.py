"""Add the agent_runs table and link messages and tool calls to the run that produced them."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

RUN_STATUSES = (
    "queued",
    "running",
    "cancel_requested",
    "cancelled",
    "completed",
    "failed",
)

AGENT_RUN_STATUS = postgresql.ENUM(
    *RUN_STATUSES,
    name="agent_run_status",
    create_type=False,
)

ACTIVE_RUN_STATUSES = ("queued", "running", "cancel_requested")

NEW_TOOL_CALL_STATUSES = ("cancelled", "unknown")

OLD_TOOL_CALL_STATUSES = ("requested", "running", "completed", "failed")


def quoted(values: tuple[str, ...]) -> str:

    """Join status values into a quoted, comma separated SQL list."""

    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:

    """Create agent_runs, then add run links and timestamps to messages and tool_calls."""

    AGENT_RUN_STATUS.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.BigInteger(),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("client_request_id", sa.String(255), nullable=True),
        sa.Column("status", AGENT_RUN_STATUS, nullable=False, server_default="queued"),
        sa.Column("worker_id", sa.String(255), nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "conversation_id",
            "client_request_id",
            name="uq_agent_runs_conversation_client_request",
        ),
    )

    op.create_index(
        "idx_agent_runs_conversation_created",
        "agent_runs",
        ["conversation_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_agent_runs_status", "agent_runs", ["status"])
    op.create_index("idx_agent_runs_worker_status", "agent_runs", ["worker_id", "status"])
    op.create_index(
        "uq_agent_runs_one_active",
        "agent_runs",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({quoted(ACTIVE_RUN_STATUSES)})"),
    )

    op.add_column("messages", sa.Column("run_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "messages",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("messages", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_messages_run_id", "messages", "agent_runs", ["run_id"], ["id"])
    op.create_index("ix_messages_run_id", "messages", ["run_id"])

    for status in NEW_TOOL_CALL_STATUSES:
        op.execute(f"ALTER TYPE tool_call_status ADD VALUE IF NOT EXISTS '{status}'")

    op.add_column("tool_calls", sa.Column("run_id", sa.BigInteger(), nullable=True))
    op.add_column("tool_calls", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tool_calls",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_foreign_key("fk_tool_calls_run_id", "tool_calls", "agent_runs", ["run_id"], ["id"])
    op.create_index("ix_tool_calls_run_id", "tool_calls", ["run_id"])


def downgrade() -> None:

    """Remove the run links and new columns, shrink tool_call_status back, then drop agent_runs."""

    op.drop_index("ix_tool_calls_run_id", table_name="tool_calls")
    op.drop_constraint("fk_tool_calls_run_id", "tool_calls", type_="foreignkey")

    for column in ("updated_at", "started_at", "run_id"):
        op.drop_column("tool_calls", column)

    op.execute(
        f"UPDATE tool_calls SET status = 'failed' WHERE status IN ({quoted(NEW_TOOL_CALL_STATUSES)})"
    )
    op.execute("ALTER TABLE tool_calls ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE tool_call_status RENAME TO tool_call_status_old")
    op.execute(f"CREATE TYPE tool_call_status AS ENUM ({quoted(OLD_TOOL_CALL_STATUSES)})")
    op.execute(
        "ALTER TABLE tool_calls ALTER COLUMN status TYPE tool_call_status "
        "USING status::text::tool_call_status"
    )
    op.execute("ALTER TABLE tool_calls ALTER COLUMN status SET DEFAULT 'requested'")
    op.execute("DROP TYPE tool_call_status_old")

    op.drop_index("ix_messages_run_id", table_name="messages")
    op.drop_constraint("fk_messages_run_id", "messages", type_="foreignkey")

    for column in ("completed_at", "updated_at", "run_id"):
        op.drop_column("messages", column)

    op.drop_index("uq_agent_runs_one_active", table_name="agent_runs")
    op.drop_index("idx_agent_runs_worker_status", table_name="agent_runs")
    op.drop_index("idx_agent_runs_status", table_name="agent_runs")
    op.drop_index("idx_agent_runs_conversation_created", table_name="agent_runs")
    op.drop_table("agent_runs")

    AGENT_RUN_STATUS.drop(op.get_bind(), checkfirst=False)
