"""Upsert the clean stocks.csv and mutual_funds.csv into the database, matching rows on ISIN."""

import argparse
from datetime import date

import psycopg

from scripts.market_data.common import clean_dir, latest_source_date, read_csv

BATCH_SIZE = 1000

STOCKS_SQL = """
INSERT INTO stocks (isin, symbol, exchange, company_name, sector, market_cap_type, is_etf, last_price, price_date)
VALUES (
    %(isin)s, %(symbol)s, %(exchange)s::stock_exchange, %(company_name)s, %(sector)s::stock_sector,
    %(market_cap_type)s::market_cap_type, %(is_etf)s, %(last_price)s, %(price_date)s
    )
ON CONFLICT (isin) DO UPDATE SET
    symbol = EXCLUDED.symbol,
    exchange = EXCLUDED.exchange,
    company_name = EXCLUDED.company_name,
    sector = COALESCE(EXCLUDED.sector, stocks.sector),
    market_cap_type = COALESCE(EXCLUDED.market_cap_type, stocks.market_cap_type),
    is_etf = EXCLUDED.is_etf,
    last_price = COALESCE(EXCLUDED.last_price, stocks.last_price),
    price_date = COALESCE(EXCLUDED.price_date, stocks.price_date),
    updated_at = now()
"""

MUTUAL_FUNDS_SQL = """
INSERT INTO mutual_funds (
    isin, amfi_scheme_code, scheme_name, base_scheme_name, amc_name, category, sub_category, plan_type, option_type, last_nav, nav_date
    )
VALUES (
    %(isin)s, %(amfi_scheme_code)s, %(scheme_name)s, %(base_scheme_name)s, %(amc_name)s, %(category)s::fund_category,
    %(sub_category)s::fund_sub_category, %(plan_type)s::fund_plan_type, %(option_type)s::fund_option_type,
    %(last_nav)s, %(nav_date)s
    )
ON CONFLICT (isin) DO UPDATE SET
    amfi_scheme_code = EXCLUDED.amfi_scheme_code,
    scheme_name = EXCLUDED.scheme_name,
    base_scheme_name = EXCLUDED.base_scheme_name,
    amc_name = EXCLUDED.amc_name,
    category = EXCLUDED.category,
    sub_category = EXCLUDED.sub_category,
    plan_type = EXCLUDED.plan_type,
    option_type = EXCLUDED.option_type,
    last_nav = EXCLUDED.last_nav,
    nav_date = EXCLUDED.nav_date,
    updated_at = now()
"""

HOLDINGS_DELETE_SQL = "DELETE FROM fund_holdings WHERE amc_name = ANY(%s)"

HOLDINGS_INSERT_SQL = """
INSERT INTO fund_holdings (
    amc_name, scheme_name, base_scheme_name, as_of_date, holding_isin, holding_name, industry, sector,
    asset_class, quantity, market_value_lakhs, weight_pct
    )
VALUES (
    %(amc_name)s, %(scheme_name)s, %(base_scheme_name)s, %(as_of_date)s, %(holding_isin)s, %(holding_name)s,
    %(industry)s, %(sector)s::stock_sector, %(asset_class)s::holding_asset_class, %(quantity)s,
    %(market_value_lakhs)s, %(weight_pct)s
    )
"""

FILL_STOCK_SECTORS_SQL = """
UPDATE stocks
SET sector = picked.sector, updated_at = now()
FROM (
    SELECT DISTINCT ON (holding_isin) holding_isin, sector
    FROM fund_holdings
    WHERE asset_class = 'equity' AND sector IS NOT NULL AND sector <> 'other'
    GROUP BY holding_isin, sector
    ORDER BY holding_isin, COUNT(*) DESC
    ) AS picked
WHERE stocks.isin = picked.holding_isin AND stocks.sector IS NULL
"""

TABLES = {
    "stocks": ("stocks.csv", STOCKS_SQL),
    "mutual_funds": ("mutual_funds.csv", MUTUAL_FUNDS_SQL),
    "fund_holdings": ("fund_holdings.csv", HOLDINGS_INSERT_SQL),
    }


def blank_to_none(row: dict[str, str]) -> dict[str, str | None]:

    """Send empty CSV cells as NULL so optional columns stay empty."""

    return {name: value or None for name, value in row.items()}


def plain_url(url: str) -> str:

    """Strip the SQLAlchemy driver part so psycopg can open the URL directly."""

    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def configured_url() -> str:

    """Read DATABASE_URL from the backend settings."""

    from app.core.config import get_settings

    url = get_settings().DATABASE_URL

    if not url:
        raise SystemExit("DATABASE_URL is not set, pass --database-url")

    return url


def push_table(
    connection: psycopg.Connection,
    sql: str,
    rows: list[dict]
    ) -> None:

    """Upsert rows in batches, committing after each batch so a failure keeps earlier batches."""

    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]

        with connection.cursor() as cursor:
            cursor.executemany(sql, batch)

        connection.commit()

        print(f"   upserted {start + len(batch)} / {len(rows)}")


def push_holdings(
    connection: psycopg.Connection,
    rows: list[dict]
    ) -> None:

    """Replace each AMC's holdings with the latest file in one transaction, then fill missing stock sectors."""

    amc_names = sorted({row["amc_name"] for row in rows})

    with connection.cursor() as cursor:
        cursor.execute(HOLDINGS_DELETE_SQL, (amc_names,))
        cursor.executemany(HOLDINGS_INSERT_SQL, rows)
        cursor.execute(FILL_STOCK_SECTORS_SQL)
        filled = cursor.rowcount

    connection.commit()

    print(f"   replaced holdings for {len(amc_names)} AMCs with {len(rows)} rows")
    print(f"   filled sector for {filled} stocks that had none")


def main() -> None:

    """Load the chosen tables from the clean folder, or with --dry-run only check the files."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--table", choices=[*TABLES, "all"], default="all")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    folder = clean_dir(args.date or latest_source_date())
    names = list(TABLES) if args.table == "all" else [args.table]

    loads = []

    for name in names:
        file_name, sql = TABLES[name]

        if not (folder / file_name).exists():
            print(f"{name}: no {file_name} in {folder}, skipped")
            continue

        rows = [blank_to_none(row) for row in read_csv(folder / file_name)][:args.limit]
        loads.append((name, sql, rows))

        print(f"{name}: {len(rows)} rows from {folder / file_name}")

    if args.dry_run:
        print("Dry run, nothing sent to the database.")
        return

    url = plain_url(args.database_url or configured_url())

    with psycopg.connect(url) as connection:

        for name, sql, rows in loads:
            print(f"Pushing {name}")

            if name == "fund_holdings":
                push_holdings(connection, rows)
                continue

            push_table(connection, sql, rows)

    print("Done.")


if __name__ == "__main__":
    main()
