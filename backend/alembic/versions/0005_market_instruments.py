"""Add the shared stocks and mutual_funds master tables, one row per instrument for all users."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

PRICE = sa.Numeric(14, 4)

STOCK_EXCHANGE = postgresql.ENUM(
    "nse",
    "bse",
    name="stock_exchange",
    create_type=False,
)

MARKET_CAP_TYPE = postgresql.ENUM(
    "large",
    "mid",
    "small",
    name="market_cap_type",
    create_type=False,
)

FUND_CATEGORY = postgresql.ENUM(
    "equity",
    "debt",
    "hybrid",
    "gold",
    "other",
    name="fund_category",
    create_type=False,
)

FUND_PLAN_TYPE = postgresql.ENUM(
    "direct",
    "regular",
    name="fund_plan_type",
    create_type=False,
)

FUND_OPTION_TYPE = postgresql.ENUM(
    "growth",
    "idcw",
    name="fund_option_type",
    create_type=False,
)

STOCK_SECTOR = postgresql.ENUM(
    "financial_services",
    "information_technology",
    "oil_gas_energy",
    "fmcg",
    "automobile",
    "healthcare",
    "metals_mining",
    "capital_goods",
    "construction",
    "consumer_durables",
    "consumer_services",
    "telecom",
    "power",
    "realty",
    "chemicals",
    "textiles",
    "media",
    "services",
    "diversified",
    "other",
    name="stock_sector",
    create_type=False,
)

FUND_SUB_CATEGORY = postgresql.ENUM(
    "large_cap",
    "mid_cap",
    "small_cap",
    "large_and_mid_cap",
    "multi_cap",
    "flexi_cap",
    "focused",
    "value",
    "contra",
    "dividend_yield",
    "elss",
    "sectoral_thematic",
    "index_fund",
    "liquid",
    "overnight",
    "ultra_short_duration",
    "low_duration",
    "money_market",
    "short_duration",
    "medium_duration",
    "long_duration",
    "dynamic_bond",
    "corporate_bond",
    "credit_risk",
    "banking_and_psu",
    "gilt",
    "floater",
    "aggressive_hybrid",
    "conservative_hybrid",
    "balanced_advantage",
    "multi_asset",
    "arbitrage",
    "equity_savings",
    "fund_of_funds",
    "solution_oriented",
    "other",
    name="fund_sub_category",
    create_type=False,
)

ENUM_TYPES = (
    STOCK_EXCHANGE,
    MARKET_CAP_TYPE,
    FUND_CATEGORY,
    FUND_PLAN_TYPE,
    FUND_OPTION_TYPE,
    STOCK_SECTOR,
    FUND_SUB_CATEGORY,
)


def timestamp_columns() -> list[sa.Column]:

    """Fresh created_at and updated_at columns, both defaulting to now."""

    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:

    """Create the instrument enum types, then stocks and mutual_funds, each unique on ISIN."""

    bind = op.get_bind()

    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=False)

    op.create_table(
        "stocks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("exchange", STOCK_EXCHANGE, nullable=True),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("sector", STOCK_SECTOR, nullable=True),
        sa.Column("market_cap_type", MARKET_CAP_TYPE, nullable=True),
        sa.Column("is_etf", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_price", PRICE, nullable=True),
        sa.Column("price_date", sa.Date(), nullable=True),
        *timestamp_columns(),
        sa.UniqueConstraint("isin", name="uq_stocks_isin"),
    )

    op.create_index("ix_stocks_symbol", "stocks", ["symbol"])

    op.create_table(
        "mutual_funds",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("amfi_scheme_code", sa.String(20), nullable=True),
        sa.Column("scheme_name", sa.String(255), nullable=False),
        sa.Column("amc_name", sa.String(100), nullable=False),
        sa.Column("category", FUND_CATEGORY, nullable=False),
        sa.Column("sub_category", FUND_SUB_CATEGORY, nullable=True),
        sa.Column("plan_type", FUND_PLAN_TYPE, nullable=False),
        sa.Column("option_type", FUND_OPTION_TYPE, nullable=False),
        sa.Column("last_nav", PRICE, nullable=True),
        sa.Column("nav_date", sa.Date(), nullable=True),
        *timestamp_columns(),
        sa.UniqueConstraint("isin", name="uq_mutual_funds_isin"),
    )

    op.create_index("ix_mutual_funds_amfi_scheme_code", "mutual_funds", ["amfi_scheme_code"])


def downgrade() -> None:

    """Drop mutual_funds and stocks with their indexes, then the enum types."""

    op.drop_index("ix_mutual_funds_amfi_scheme_code", table_name="mutual_funds")
    op.drop_table("mutual_funds")
    op.drop_index("ix_stocks_symbol", table_name="stocks")
    op.drop_table("stocks")

    bind = op.get_bind()

    for enum_type in reversed(ENUM_TYPES):
        enum_type.drop(bind, checkfirst=False)
