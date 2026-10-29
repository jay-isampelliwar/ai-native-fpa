"""Add run_events: every event of a run saved in order, so a listener on any API process can catch up after a reconnect."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:

    """Create run_events, unique on the run and its event number, removed with its run."""

    op.create_table(
        "run_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("run_id", sa.BigInteger(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "seq", name="uq_run_events_run_seq"),
        )

    op.create_index("idx_run_events_created", "run_events", ["created_at"])


def downgrade() -> None:

    """Drop run_events."""

    op.drop_index("idx_run_events_created", table_name="run_events")
    op.drop_table("run_events")
