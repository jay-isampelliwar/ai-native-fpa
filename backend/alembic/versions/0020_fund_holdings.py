"""Add fund_holdings for each scheme's latest monthly portfolio, plus a per-scheme sector split view."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

STOCK_SECTOR = postgresql.ENUM(name="stock_sector", create_type=False)

HOLDING_ASSET_CLASS = postgresql.ENUM(
    "equity",
    "debt",
    "fund_units",
    "cash_and_other",
    name="holding_asset_class",
    create_type=False,
    )

SECTOR_VIEW_SQL = """
CREATE VIEW fund_sector_allocation AS
SELECT
    base_scheme_name,
    amc_name,
    as_of_date,
    COALESCE(sector::text, 'other') AS sector,
    SUM(weight_pct) AS weight_pct,
    COUNT(*) AS holdings
FROM fund_holdings
WHERE asset_class = 'equity' AND base_scheme_name IS NOT NULL
GROUP BY base_scheme_name, amc_name, as_of_date, COALESCE(sector::text, 'other')
"""


def upgrade() -> None:

    """Link plans to their scheme, create fund_holdings and the sector split view."""

    op.add_column("mutual_funds", sa.Column("base_scheme_name", sa.String(255), nullable=True))
    op.create_index("ix_mutual_funds_base_scheme_name", "mutual_funds", ["base_scheme_name"])

    HOLDING_ASSET_CLASS.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "fund_holdings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("amc_name", sa.String(100), nullable=False),
        sa.Column("scheme_name", sa.String(255), nullable=False),
        sa.Column("base_scheme_name", sa.String(255), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("holding_isin", sa.String(12), nullable=True),
        sa.Column("holding_name", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("sector", STOCK_SECTOR, nullable=True),
        sa.Column("asset_class", HOLDING_ASSET_CLASS, nullable=False),
        sa.Column("quantity", sa.Numeric(20, 4), nullable=True),
        sa.Column("market_value_lakhs", sa.Numeric(18, 4), nullable=True),
        sa.Column("weight_pct", sa.Numeric(9, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    op.create_index("ix_fund_holdings_base_scheme_name", "fund_holdings", ["base_scheme_name"])
    op.create_index("ix_fund_holdings_holding_isin", "fund_holdings", ["holding_isin"])
    op.create_index("ix_fund_holdings_amc_name", "fund_holdings", ["amc_name"])

    op.execute(SECTOR_VIEW_SQL)


def downgrade() -> None:

    """Drop the view, fund_holdings, its enum and the scheme link on mutual_funds."""

    op.execute("DROP VIEW fund_sector_allocation")
    op.drop_index("ix_fund_holdings_amc_name", table_name="fund_holdings")
    op.drop_index("ix_fund_holdings_holding_isin", table_name="fund_holdings")
    op.drop_index("ix_fund_holdings_base_scheme_name", table_name="fund_holdings")
    op.drop_table("fund_holdings")

    HOLDING_ASSET_CLASS.drop(op.get_bind(), checkfirst=False)

    op.drop_index("ix_mutual_funds_base_scheme_name", table_name="mutual_funds")
    op.drop_column("mutual_funds", "base_scheme_name")
