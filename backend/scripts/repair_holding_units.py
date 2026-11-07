"""Fix holdings whose units no longer match their saved value, by setting units to current_value over the latest NAV or price."""

import argparse
from decimal import ROUND_DOWN, Decimal

import psycopg

from app.core.config import get_settings


FIND_SQL = """
SELECT h.id, h.user_id, h.units, h.invested_amount, h.current_value,
       COALESCE(f.scheme_name, s.company_name) AS name,
       COALESCE(f.last_nav, s.last_price) AS price,
       (h.mutual_fund_id IS NOT NULL) AS is_fund
FROM holdings h
LEFT JOIN mutual_funds f ON f.id = h.mutual_fund_id
LEFT JOIN stocks s ON s.id = h.stock_id
WHERE h.current_value IS NOT NULL
  AND COALESCE(f.last_nav, s.last_price) > 0
  AND (%(user_id)s::bigint IS NULL OR h.user_id = %(user_id)s::bigint)
ORDER BY h.id
"""

FIX_SQL = """
UPDATE holdings
SET units = %(units)s,
    avg_buy_price = CASE WHEN invested_amount IS NULL THEN NULL ELSE round(invested_amount / %(units)s, 4) END,
    as_of_date = CURRENT_DATE,
    updated_at = now()
WHERE id = %(id)s
"""

DRIFT = Decimal("0.01")

FUND_STEP = Decimal("0.001")

WHOLE = Decimal("1")


def database_url(given: str | None) -> str:

    """The URL passed on the command line, else DATABASE_URL from the settings, in plain libpq form."""

    url = given or get_settings().DATABASE_URL

    if not url:
        raise SystemExit("DATABASE_URL is not set, pass --database-url")

    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def drifted(row: dict) -> bool:

    """True when units times the latest price is more than one percent away from the saved current value."""

    worth = Decimal(row["units"]) * Decimal(row["price"])

    return abs(worth - Decimal(row["current_value"])) > Decimal(row["current_value"]) * DRIFT


def right_units(row: dict) -> Decimal:

    """The units the saved current value buys at the latest price: three decimals for a fund, whole shares for a stock."""

    step = FUND_STEP if row["is_fund"] else WHOLE

    return (Decimal(row["current_value"]) / Decimal(row["price"])).quantize(step, rounding=ROUND_DOWN)


def main() -> None:

    """List every drifted holding with its old and new units, and change them only with --apply."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    with psycopg.connect(database_url(args.database_url), row_factory=psycopg.rows.dict_row) as connection:

        rows = [row for row in connection.execute(FIND_SQL, {"user_id": args.user_id}) if drifted(row)]

        if not rows:
            print("Every holding's units match its saved value. Nothing to do.")
            return

        for row in rows:

            units = right_units(row)

            print(
                f"holding {row['id']} (user {row['user_id']}) {row['name']}: "
                f"units {row['units']} -> {units}, worth {Decimal(row['units']) * Decimal(row['price']):.2f} -> {row['current_value']}"
                )

            if args.apply:
                connection.execute(FIX_SQL, {"id": row["id"], "units": units})

        if args.apply:
            connection.commit()
            print(f"Fixed {len(rows)} holding(s).")

        else:
            print(f"{len(rows)} holding(s) would change. Run again with --apply to fix them.")


if __name__ == "__main__":
    main()
