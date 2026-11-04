"""Add a holdings section to data_coverage, so the planner asks about stocks and mutual funds like any other section."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

COVERAGE_STATUS = postgresql.ENUM(name="coverage_status", create_type=False)


def upgrade() -> None:

    """Add the holdings status column, pending for every user."""

    op.add_column(
        "data_coverage",
        sa.Column("holdings", COVERAGE_STATUS, nullable=False, server_default="pending"),
        )


def downgrade() -> None:

    """Drop the holdings status column."""

    op.drop_column("data_coverage", "holdings")
