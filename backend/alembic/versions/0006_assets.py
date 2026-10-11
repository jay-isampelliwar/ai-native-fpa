"""Add the user's asset tables: bank accounts, deposits, holdings, SIPs, retirement and physical assets."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(14, 2)

RATE = sa.Numeric(5, 2)

PRICE = sa.Numeric(14, 4)

UNITS = sa.Numeric(18, 4)

BANK_ACCOUNT_TYPE = postgresql.ENUM(
    "savings",
    "current",
    "salary",
    name="bank_account_type",
    create_type=False,
)

DEPOSIT_TYPE = postgresql.ENUM(
    "fd",
    "rd",
    name="deposit_type",
    create_type=False,
)

HOLDING_ASSET_TYPE = postgresql.ENUM(
    "stock",
    "mutual_fund",
    name="holding_asset_type",
    create_type=False,
)

RETIREMENT_ACCOUNT_TYPE = postgresql.ENUM(
    "epf",
    "ppf",
    "nps",
    "vpf",
    name="retirement_account_type",
    create_type=False,
)

PHYSICAL_ASSET_TYPE = postgresql.ENUM(
    "real_estate",
    "gold",
    "vehicle",
    "other",
    name="physical_asset_type",
    create_type=False,
)

ENUM_TYPES = (
    BANK_ACCOUNT_TYPE,
    DEPOSIT_TYPE,
    HOLDING_ASSET_TYPE,
    RETIREMENT_ACCOUNT_TYPE,
    PHYSICAL_ASSET_TYPE,
)

TABLES = (
    "bank_accounts",
    "fixed_deposits",
    "holdings",
    "sip_plans",
    "retirement_accounts",
    "physical_assets",
)

ONE_INSTRUMENT_PER_HOLDING = (
    "(asset_type = 'stock' AND stock_id IS NOT NULL AND mutual_fund_id IS NULL) OR "
    "(asset_type = 'mutual_fund' AND mutual_fund_id IS NOT NULL AND stock_id IS NULL)"
)


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

    """Create the asset enum types, then the six asset tables and their lookup indexes."""

    bind = op.get_bind()

    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=False)

    op.create_table(
        "bank_accounts",
        *owner_columns(),
        sa.Column("bank_name", sa.String(100), nullable=False),
        sa.Column("account_type", BANK_ACCOUNT_TYPE, nullable=False),
        sa.Column("balance", MONEY, nullable=False),
        sa.Column("interest_rate", RATE, nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        *timestamp_columns(),
    )

    op.create_table(
        "fixed_deposits",
        *owner_columns(),
        sa.Column("bank_name", sa.String(100), nullable=False),
        sa.Column("deposit_type", DEPOSIT_TYPE, nullable=False),
        sa.Column("principal", MONEY, nullable=False),
        sa.Column("interest_rate", RATE, nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("maturity_date", sa.Date(), nullable=False),
        sa.Column("maturity_amount", MONEY, nullable=True),
        *timestamp_columns(),
    )

    op.create_table(
        "holdings",
        *owner_columns(),
        sa.Column("asset_type", HOLDING_ASSET_TYPE, nullable=False),
        sa.Column("stock_id", sa.BigInteger(), sa.ForeignKey("stocks.id"), nullable=True),
        sa.Column("mutual_fund_id", sa.BigInteger(), sa.ForeignKey("mutual_funds.id"), nullable=True),
        sa.Column("folio_number", sa.String(30), nullable=True),
        sa.Column("units", UNITS, nullable=False),
        sa.Column("avg_buy_price", PRICE, nullable=True),
        sa.Column("invested_amount", MONEY, nullable=True),
        sa.Column("current_value", MONEY, nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(ONE_INSTRUMENT_PER_HOLDING, name="ck_holdings_one_instrument"),
    )

    op.create_index("ix_holdings_stock_id", "holdings", ["stock_id"])
    op.create_index("ix_holdings_mutual_fund_id", "holdings", ["mutual_fund_id"])

    op.create_table(
        "sip_plans",
        *owner_columns(),
        sa.Column("holding_id", sa.BigInteger(), sa.ForeignKey("holdings.id"), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("sip_day", sa.SmallInteger(), nullable=False),
        sa.Column("step_up_rate", RATE, nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamp_columns(),
        sa.CheckConstraint("sip_day BETWEEN 1 AND 28", name="ck_sip_plans_sip_day"),
    )

    op.create_index("ix_sip_plans_holding_id", "sip_plans", ["holding_id"])

    op.create_table(
        "retirement_accounts",
        *owner_columns(),
        sa.Column("account_type", RETIREMENT_ACCOUNT_TYPE, nullable=False),
        sa.Column("balance", MONEY, nullable=False),
        sa.Column("monthly_contribution", MONEY, nullable=True),
        sa.Column("employer_contribution", MONEY, nullable=True),
        sa.Column("interest_rate", RATE, nullable=True),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        *timestamp_columns(),
    )

    op.create_table(
        "physical_assets",
        *owner_columns(),
        sa.Column("asset_type", PHYSICAL_ASSET_TYPE, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("purchase_value", MONEY, nullable=True),
        sa.Column("current_value", MONEY, nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("is_self_occupied", sa.Boolean(), nullable=False, server_default=sa.false()),
        *timestamp_columns(),
    )

    for table in TABLES:
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])


def downgrade() -> None:

    """Drop the six asset tables children first, then the enum types."""

    op.drop_index("ix_sip_plans_holding_id", table_name="sip_plans")
    op.drop_index("ix_holdings_mutual_fund_id", table_name="holdings")
    op.drop_index("ix_holdings_stock_id", table_name="holdings")

    for table in reversed(TABLES):

        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_table(table)

    bind = op.get_bind()

    for enum_type in reversed(ENUM_TYPES):
        enum_type.drop(bind, checkfirst=False)
