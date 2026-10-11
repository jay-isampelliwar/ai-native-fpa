"""Add the net_worth_snapshots table, one row per user per date, for the net worth trend."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(14, 2)


def upgrade() -> None:

    """Create net_worth_snapshots, unique on user and snapshot date."""

    op.create_table(
        "net_worth_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("total_assets", MONEY, nullable=False),
        sa.Column("total_liabilities", MONEY, nullable=False),
        sa.Column("net_worth", MONEY, nullable=False),
        sa.Column("breakdown", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "snapshot_date", name="uq_net_worth_snapshots_user_date"),
    )


def downgrade() -> None:

    """Drop net_worth_snapshots."""

    op.drop_table("net_worth_snapshots")
