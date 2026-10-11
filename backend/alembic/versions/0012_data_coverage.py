"""Add the data_coverage table: one row per user saying, per section, whether data is given, none, declined or pending."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

COVERAGE_STATUS = postgresql.ENUM(
    "pending",
    "provided",
    "none",
    "declined",
    name="coverage_status",
    create_type=False,
)

SECTIONS = (
    "profile",
    "family",
    "income",
    "expenses",
    "bank_accounts",
    "fixed_deposits",
    "retirement_accounts",
    "physical_assets",
    "loans",
    "credit_cards",
    "insurance",
    "goals",
    "tax_profile",
)


def upgrade() -> None:

    """Create the coverage_status enum, then data_coverage with every section pending by default."""

    COVERAGE_STATUS.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "data_coverage",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True),
        *[sa.Column(section, COVERAGE_STATUS, nullable=False, server_default="pending") for section in SECTIONS],
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:

    """Drop data_coverage, then the enum type."""

    op.drop_table("data_coverage")

    COVERAGE_STATUS.drop(op.get_bind(), checkfirst=False)
