"""Turn the AMFI NAV and scheme files into one clean mutual_funds.csv, one row per active plan and option."""

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.market_data.common import (
    clean_dir,
    latest_source_date,
    preview,
    read_csv,
    source_dir,
    write_csv,
    )

COLUMNS = [
    "isin",
    "amfi_scheme_code",
    "scheme_name",
    "base_scheme_name",
    "amc_name",
    "category",
    "sub_category",
    "plan_type",
    "option_type",
    "last_nav",
    "nav_date",
    ]

ACTIVE_WITHIN_DAYS = 30

SCHEME_NAME_LIMIT = 255

AMC_NAME_LIMIT = 100

SUB_CATEGORY_RULES = (
    ("large & mid", "large_and_mid_cap"),
    ("large cap", "large_cap"),
    ("mid cap", "mid_cap"),
    ("small cap", "small_cap"),
    ("multi cap", "multi_cap"),
    ("flexi cap", "flexi_cap"),
    ("focused", "focused"),
    ("value", "value"),
    ("contra", "contra"),
    ("dividend yield", "dividend_yield"),
    ("elss", "elss"),
    ("sectoral", "sectoral_thematic"),
    ("thematic", "sectoral_thematic"),
    ("index fund", "index_fund"),
    ("ultra short to short", "other"),
    ("ultra short", "ultra_short_duration"),
    ("low duration", "low_duration"),
    ("money market", "money_market"),
    ("liquid", "liquid"),
    ("overnight", "overnight"),
    ("short duration", "short_duration"),
    ("short term", "short_duration"),
    ("medium to long", "long_duration"),
    ("medium duration", "medium_duration"),
    ("medium term", "medium_duration"),
    ("long duration", "long_duration"),
    ("long term", "long_duration"),
    ("dynamic bond", "dynamic_bond"),
    ("dynamic term", "dynamic_bond"),
    ("corporate bond", "corporate_bond"),
    ("credit risk", "credit_risk"),
    ("banking and psu", "banking_and_psu"),
    ("gilt", "gilt"),
    ("floating", "floater"),
    ("floater", "floater"),
    ("aggressive hybrid", "aggressive_hybrid"),
    ("conservative hybrid", "conservative_hybrid"),
    ("balanced advantage", "balanced_advantage"),
    ("dynamic asset", "balanced_advantage"),
    ("multi asset", "multi_asset"),
    ("arbitrage", "arbitrage"),
    ("equity savings", "equity_savings"),
    ("fof", "fund_of_funds"),
    ("fund of funds", "fund_of_funds"),
    ("retirement", "solution_oriented"),
    ("children", "solution_oriented"),
    ("solution oriented", "solution_oriented"),
    )

DEBT_NAME_WORDS = ("gilt", "sdl", "bond", "debt", "g-sec", "gsec", "crisil-ibx", "crisil ibx", "treasury", "psu", "liquid")


def is_etf(category: str) -> bool:

    """True for exchange traded funds, which live in the stocks table instead."""

    return "etf" in category.lower()


def sub_category_for(category: str) -> str:

    """Pick our sub_category enum from the AMFI category text using the first matching rule."""

    text = category.lower()

    for words, sub_category in SUB_CATEGORY_RULES:

        if words in text:
            return sub_category

    return "other"


def category_for(
    category: str,
    name: str
    ) -> str:

    """Pick equity, debt, hybrid, gold or other from the AMFI category and the scheme name."""

    text = category.lower()
    lowered_name = name.lower()

    if "gold" in text or "gold" in lowered_name:
        return "gold"

    if "hybrid" in text or "arbitrage" in text or "equity savings" in text or "multi asset" in text:
        return "hybrid"

    if "debt" in text or "income" in text:
        return "debt"

    if "fof" in text or "fund of funds" in text:
        return "other"

    if "index fund" in text:
        return "debt" if any(word in lowered_name for word in DEBT_NAME_WORDS) else "equity"

    if "equity" in text or "elss" in text:
        return "equity"

    return "other"


def plan_for(
    plan: str,
    name: str
    ) -> str:

    """Direct or regular, from the plan column and the scheme name together."""

    return "direct" if "direct" in f"{plan} {name}".lower() else "regular"


def option_for(
    option: str,
    name: str
    ) -> str:

    """Growth or idcw, from the option column and the scheme name together."""

    text = f"{option} {name}".lower()

    if "idcw" in text or "dividend" in text or "income distribution" in text or "bonus" in text:
        return "idcw"

    return "growth"


def read_nav_rows(path: Path) -> list[list[str]]:

    """Return the data lines of NAVAll.txt split on semicolons, skipping AMC and category headings."""

    rows = []

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = [part.strip() for part in line.split(";")]

        if len(parts) < 8 or parts[0] == "Scheme Code":
            continue

        rows.append(parts)

    return rows


def pick_isin(parts: list[str]) -> str:

    """Prefer the payout or growth ISIN, falling back to the reinvestment ISIN."""

    for isin in (parts[1], parts[2]):

        if isin.startswith("INF") and len(isin) == 12:
            return isin

    return ""


def build(
    folder: Path,
    limit: int | None
    ) -> list[dict]:

    """Build one row per active, non-ETF plan and option from the files in one sources folder."""

    amfi_folder = folder / "amfi"
    schemes = {row["Code"]: row for row in read_csv(amfi_folder / "SchemeData.csv")}
    nav_rows = read_nav_rows(amfi_folder / "NAVAll.txt")

    dated = [(parts, datetime.strptime(parts[7], "%d-%b-%Y").date()) for parts in nav_rows]
    newest = max(nav_date for _, nav_date in dated)
    cutoff = newest - timedelta(days=ACTIVE_WITHIN_DAYS)

    funds: dict[str, dict] = {}

    for parts, nav_date in dated:

        if nav_date < cutoff:
            continue

        code, _, _, name, plan, option, nav = parts[:7]
        scheme = schemes.get(code, {})
        category = scheme.get("Scheme Category", "")
        isin = pick_isin(parts)

        if not isin or is_etf(category):
            continue

        try:
            float(nav)

        except ValueError:
            continue

        full_name = scheme.get("Scheme NAV Name") or name

        funds.setdefault(isin, {
            "isin": isin,
            "amfi_scheme_code": code,
            "scheme_name": full_name[:SCHEME_NAME_LIMIT],
            "base_scheme_name": (scheme.get("Scheme Name") or name)[:SCHEME_NAME_LIMIT],
            "amc_name": scheme.get("AMC", "")[:AMC_NAME_LIMIT],
            "category": category_for(category, name),
            "sub_category": sub_category_for(category),
            "plan_type": plan_for(plan, full_name),
            "option_type": option_for(option, full_name),
            "last_nav": nav,
            "nav_date": nav_date.isoformat(),
            })

        if limit and len(funds) >= limit:
            break

    return list(funds.values())


def main() -> None:

    """Build mutual_funds.csv, or with --limit only print a small sample without writing anything."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    run_date = args.date or latest_source_date()
    rows = build(source_dir(run_date), args.limit)

    preview("mutual_funds", rows, args.limit or 5)

    if args.limit:
        print("\nTest run with --limit, nothing written.")
        return

    target = clean_dir(run_date) / "mutual_funds.csv"
    write_csv(target, COLUMNS, rows)

    categories: dict[str, int] = {}

    for row in rows:
        categories[row["category"]] = categories.get(row["category"], 0) + 1

    print(f"\nWrote {target}")
    print(f"   by category: {categories}")
    print(f"   unique AMCs: {len({row['amc_name'] for row in rows})}")


if __name__ == "__main__":
    main()
