"""Add the planning tables: goals, goal_allocations, assumptions and tax_profile."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(14, 2)

RATE = sa.Numeric(5, 2)

GOAL_TYPE = postgresql.ENUM(
    "retirement",
    "education",
    "house",
    "marriage",
    "emergency",
    "vehicle",
    "travel",
    "other",
    name="goal_type",
    create_type=False,
)

GOAL_STATUS = postgresql.ENUM(
    "active",
    "achieved",
    "dropped",
    name="goal_status",
    create_type=False,
)

GOAL_ASSET_TABLE = postgresql.ENUM(
    "holdings",
    "fixed_deposits",
    "retirement_accounts",
    "bank_accounts",
    name="goal_asset_table",
    create_type=False,
)

TAX_REGIME = postgresql.ENUM(
    "old",
    "new",
    name="tax_regime",
    create_type=False,
)

ASSUMPTION_KEY = postgresql.ENUM(
    "inflation",
    "education_inflation",
    "medical_inflation",
    "equity_return",
    "debt_return",
    "gold_return",
    "real_estate_return",
    "salary_growth",
    "post_retirement_return",
    name="assumption_key",
    create_type=False,
)

ENUM_TYPES = (GOAL_TYPE, GOAL_STATUS, GOAL_ASSET_TABLE, TAX_REGIME, ASSUMPTION_KEY)

TABLES = ("goals", "goal_allocations", "assumptions", "tax_profile")


def owner_columns() -> list[sa.Column]:

    """Fresh id and user_id columns that every table owned by one user starts with."""

    return [
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
    ]


def timestamp_columns() -> list[sa.Column]:

    """Fresh created_at and updated_at columns, both defaulting to now."""

    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:

    """Create the planning enum types, then the four planning tables and their indexes."""

    bind = op.get_bind()

    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=False)

    op.create_table(
        "goals",
        *owner_columns(),
        sa.Column("goal_type", GOAL_TYPE, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("target_amount", MONEY, nullable=False),
        sa.Column("target_year", sa.SmallInteger(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("inflation_rate", RATE, nullable=True),
        sa.Column("family_member_id", sa.BigInteger(), sa.ForeignKey("family_members.id"), nullable=True),
        sa.Column("status", GOAL_STATUS, nullable=False, server_default="active"),
        *timestamp_columns(),
    )

    op.create_table(
        "goal_allocations",
        *owner_columns(),
        sa.Column("goal_id", sa.BigInteger(), sa.ForeignKey("goals.id"), nullable=False),
        sa.Column("asset_table", GOAL_ASSET_TABLE, nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("allocation_pct", RATE, nullable=False),
        *timestamp_columns(),
        sa.UniqueConstraint("goal_id", "asset_table", "asset_id", name="uq_goal_allocations_goal_asset"),
        sa.CheckConstraint(
            "allocation_pct > 0 AND allocation_pct <= 100",
            name="ck_goal_allocations_allocation_pct",
        ),
    )

    op.create_index("ix_goal_allocations_asset", "goal_allocations", ["asset_table", "asset_id"])

    op.create_table(
        "assumptions",
        *owner_columns(),
        sa.Column("key", ASSUMPTION_KEY, nullable=False),
        sa.Column("value", RATE, nullable=False),
        *timestamp_columns(),
        sa.UniqueConstraint("user_id", "key", name="uq_assumptions_user_key"),
    )

    op.create_table(
        "tax_profile",
        *owner_columns(),
        sa.Column("financial_year", sa.String(9), nullable=False),
        sa.Column("regime", TAX_REGIME, nullable=False),
        sa.Column("sec_80c_used", MONEY, nullable=False, server_default="0"),
        sa.Column("sec_80d_used", MONEY, nullable=False, server_default="0"),
        sa.Column("hra_claimed", MONEY, nullable=False, server_default="0"),
        *timestamp_columns(),
        sa.UniqueConstraint("user_id", "financial_year", name="uq_tax_profile_user_year"),
    )

    for table in ("goals", "goal_allocations"):
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])


def downgrade() -> None:

    """Drop the four planning tables children first, then the enum types."""

    op.drop_index("ix_goal_allocations_user_id", table_name="goal_allocations")
    op.drop_index("ix_goals_user_id", table_name="goals")
    op.drop_index("ix_goal_allocations_asset", table_name="goal_allocations")

    for table in reversed(TABLES):
        op.drop_table(table)

    bind = op.get_bind()

    for enum_type in reversed(ENUM_TYPES):
        enum_type.drop(bind, checkfirst=False)
