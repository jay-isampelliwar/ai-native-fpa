"""Add the insurance_policies table for term, health, life and other covers."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(14, 2)

POLICY_TYPE = postgresql.ENUM(
    "term",
    "health",
    "life",
    "ulip",
    "vehicle",
    "other",
    name="policy_type",
    create_type=False,
)

PAYMENT_FREQUENCY = postgresql.ENUM(
    "monthly",
    "quarterly",
    "half_yearly",
    "yearly",
    name="payment_frequency",
    create_type=False,
)


def upgrade() -> None:

    """Create the policy_type enum, then insurance_policies reusing the cash flow payment_frequency enum."""

    POLICY_TYPE.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "insurance_policies",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("policy_type", POLICY_TYPE, nullable=False),
        sa.Column("insurer", sa.String(100), nullable=False),
        sa.Column("policy_name", sa.String(255), nullable=True),
        sa.Column("cover_amount", MONEY, nullable=False),
        sa.Column("premium", MONEY, nullable=False),
        sa.Column("premium_frequency", PAYMENT_FREQUENCY, nullable=False, server_default="yearly"),
        sa.Column("family_member_id", sa.BigInteger(), sa.ForeignKey("family_members.id"), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("renewal_date", sa.Date(), nullable=True),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_insurance_policies_user_id", "insurance_policies", ["user_id"])


def downgrade() -> None:

    """Drop insurance_policies, then the policy_type enum, leaving payment_frequency to its own revision."""

    op.drop_index("ix_insurance_policies_user_id", table_name="insurance_policies")
    op.drop_table("insurance_policies")

    POLICY_TYPE.drop(op.get_bind(), checkfirst=False)
