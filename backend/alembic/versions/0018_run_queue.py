"""Add what the run queue needs to agent_runs: when the job was sent, how many times a worker took it, and indexes for the stale and unsent checks."""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:

    """Add enqueued_at and attempts, and the partial indexes the worker's sweeps read."""

    op.add_column("agent_runs", sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))

    op.create_index(
        "idx_agent_runs_heartbeat",
        "agent_runs",
        ["heartbeat_at"],
        postgresql_where=sa.text("status IN ('running', 'cancel_requested')"),
        )

    op.create_index(
        "idx_agent_runs_queued_unsent",
        "agent_runs",
        ["created_at"],
        postgresql_where=sa.text("status = 'queued' AND enqueued_at IS NULL"),
        )


def downgrade() -> None:

    """Drop the two indexes and the two columns."""

    op.drop_index("idx_agent_runs_queued_unsent", table_name="agent_runs")
    op.drop_index("idx_agent_runs_heartbeat", table_name="agent_runs")

    op.drop_column("agent_runs", "attempts")
    op.drop_column("agent_runs", "enqueued_at")
