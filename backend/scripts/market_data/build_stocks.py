"""Merge the NSE, BSE and AMFI files into one clean stocks.csv, one row per ISIN."""

import argparse
from datetime import date, datetime
from pathlib import Path

import openpyxl

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
    "symbol",
    "exchange",
    "company_name",
    "sector",
    "market_cap_type",
    "is_etf",
    "last_price",
    "price_date",
    ]

NSE_PRICE_SERIES = ("EQ", "BE", "BZ", "SM", "ST")

BSE_EQUITY_SERIES = {"A", "B", "T", "X", "XT", "M", "MT", "Z", "E", "P", "ZP", "R", "MS", "TS", "XD"}

INDUSTRY_FILES = (
    "ind_nifty500list.csv",
    "ind_niftytotalmarket_list.csv",
    "ind_niftymicrocap250_list.csv",
    )

SECTOR_BY_INDUSTRY = {
    "financial services": "financial_services",
    "information technology": "information_technology",
    "oil gas & consumable fuels": "oil_gas_energy",
    "fast moving consumer goods": "fmcg",
    "automobile and auto components": "automobile",
    "healthcare": "healthcare",
    "metals & mining": "metals_mining",
    "capital goods": "capital_goods",
    "construction": "construction",
    "construction materials": "construction",
    "consumer durables": "consumer_durables",
    "consumer services": "consumer_services",
    "telecommunication": "telecom",
    "power": "power",
    "realty": "realty",
    "chemicals": "chemicals",
    "textiles": "textiles",
    "media entertainment & publication": "media",
    "services": "services",
    "diversified": "diversified",
    }

MARKET_CAP_BY_LABEL = {
    "large cap": "large",
    "mid cap": "mid",
    "small cap": "small",
    }

NAME_LIMIT = 255

SYMBOL_LIMIT = 50

EQUITY_SHARE_CODE = "01"


def is_equity_share(isin: str) -> bool:

    """True for an Indian equity share ISIN, false for rights entitlements, bonds and the like."""

    return isin.startswith("INE") and len(isin) == 12 and isin[7:9] == EQUITY_SHARE_CODE


def find_one(
    folder: Path,
    pattern: str
    ) -> Path | None:

    """Return the newest file in a folder matching a glob, or None."""

    matches = sorted(folder.glob(pattern))

    return matches[-1] if matches else None


def load_sectors(nse_folder: Path) -> dict[str, str]:

    """Map ISIN to our sector enum using the industry column of the NSE index files."""

    sectors: dict[str, str] = {}

    for name in INDUSTRY_FILES:
        path = nse_folder / name

        if not path.exists():
            continue

        for row in read_csv(path):
            sector = SECTOR_BY_INDUSTRY.get(row["Industry"].lower(), "other")
            sectors.setdefault(row["ISIN Code"], sector)

    return sectors


def load_market_caps(amfi_folder: Path) -> dict[str, str]:

    """Map ISIN to large, mid or small from the AMFI half-yearly market cap sheet."""

    path = find_one(amfi_folder, "AverageMarketCapitalization*.xlsx")

    if path is None:
        return {}

    sheet = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    rows = sheet.iter_rows(values_only=True)

    header: list[str] = []

    for row in rows:

        if row and "ISIN" in row:
            header = [str(cell or "").strip() for cell in row]
            break

    isin_at = header.index("ISIN")
    label_at = next(i for i, name in enumerate(header) if name.lower().startswith("categorization"))

    caps: dict[str, str] = {}

    for row in rows:
        label = MARKET_CAP_BY_LABEL.get(str(row[label_at] or "").strip().lower())

        if label and row[isin_at]:
            caps[str(row[isin_at]).strip()] = label

    return caps


def load_fund_names(amfi_folder: Path) -> dict[str, str]:

    """Map fund ISIN to its AMFI scheme name, used to give ETFs a readable name."""

    path = amfi_folder / "NAVAll.txt"

    if not path.exists():
        return {}

    names: dict[str, str] = {}

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.split(";")

        if len(parts) < 8:
            continue

        for isin in (parts[1].strip(), parts[2].strip()):

            if isin.startswith("INF"):
                names.setdefault(isin, parts[3].strip())

    return names


def load_nse_prices(nse_folder: Path) -> tuple[dict[str, str], date | None]:

    """Map NSE symbol to closing price, preferring the normal EQ series."""

    path = find_one(nse_folder, "sec_bhavdata_full_*.csv")

    if path is None:
        return {}, None

    prices: dict[str, tuple[int, str]] = {}
    price_date = None

    for row in read_csv(path):
        series = row["SERIES"]

        if series not in NSE_PRICE_SERIES:
            continue

        rank = NSE_PRICE_SERIES.index(series)
        current = prices.get(row["SYMBOL"])

        if current is None or rank < current[0]:
            prices[row["SYMBOL"]] = (rank, row["CLOSE_PRICE"])

        price_date = datetime.strptime(row["DATE1"], "%d-%b-%Y").date()

    return {symbol: price for symbol, (_, price) in prices.items()}, price_date


def load_bse_rows(bse_folder: Path) -> list[dict[str, str]]:

    """Return BSE equity rows only, dropping bonds, government securities and trusts."""

    path = find_one(bse_folder, "BhavCopy_BSE_CM_*.csv")

    if path is None:
        return []

    return [
        row for row in read_csv(path)
        if row["FinInstrmTp"] == "STK"
        and row["SctySrs"] in BSE_EQUITY_SERIES
        and is_equity_share(row["ISIN"])
        ]


def nse_stock_rows(
    nse_folder: Path,
    limit: int | None
    ) -> list[dict]:

    """Read the NSE main board and SME lists into our column names."""

    rows = []

    main_board = read_csv(nse_folder / "EQUITY_L.csv")[:limit]
    sme_board = read_csv(nse_folder / "SME_EQUITY_L.csv")[:limit]

    for row in main_board:
        rows.append({"isin": row["ISIN NUMBER"], "symbol": row["SYMBOL"], "company_name": row["NAME OF COMPANY"]})

    for row in sme_board:
        rows.append({"isin": row["ISIN_NUMBER"], "symbol": row["SYMBOL"], "company_name": row["NAME_OF_COMPANY"]})

    return [row for row in rows if is_equity_share(row["isin"])]


def build(
    folder: Path,
    limit: int | None
    ) -> list[dict]:

    """Build every stock and ETF row from the files in one sources folder."""

    nse_folder = folder / "nse"
    amfi_folder = folder / "amfi"

    sectors = load_sectors(nse_folder)
    caps = load_market_caps(amfi_folder)
    fund_names = load_fund_names(amfi_folder)
    nse_prices, nse_price_date = load_nse_prices(nse_folder)
    bse_rows = load_bse_rows(folder / "bse")

    bse_price_by_isin = {row["ISIN"]: (row["ClsPric"], row["TradDt"]) for row in bse_rows}

    stocks: dict[str, dict] = {}

    for row in nse_stock_rows(nse_folder, limit):
        isin = row["isin"]
        price = nse_prices.get(row["symbol"])
        bse_price = bse_price_by_isin.get(isin)

        stocks.setdefault(isin, {
            **row,
            "exchange": "nse",
            "sector": sectors.get(isin, ""),
            "market_cap_type": caps.get(isin, "small"),
            "is_etf": "false",
            "last_price": price or (bse_price[0] if bse_price else ""),
            "price_date": (nse_price_date.isoformat() if price and nse_price_date else bse_price[1] if bse_price else ""),
            })

    for row in read_csv(nse_folder / "eq_etfseclist.csv")[:limit]:
        isin = row["ISINNumber"]
        price = nse_prices.get(row["Symbol"])

        stocks.setdefault(isin, {
            "isin": isin,
            "symbol": row["Symbol"],
            "exchange": "nse",
            "company_name": fund_names.get(isin) or row["Underlying Asset"] or row["SecurityName"],
            "sector": "",
            "market_cap_type": "",
            "is_etf": "true",
            "last_price": price or "",
            "price_date": nse_price_date.isoformat() if price and nse_price_date else "",
            })

    for row in bse_rows[:limit]:
        isin = row["ISIN"]

        stocks.setdefault(isin, {
            "isin": isin,
            "symbol": row["TckrSymb"],
            "exchange": "bse",
            "company_name": row["FinInstrmNm"],
            "sector": sectors.get(isin, ""),
            "market_cap_type": caps.get(isin, "small"),
            "is_etf": "false",
            "last_price": row["ClsPric"],
            "price_date": row["TradDt"],
            })

    for row in stocks.values():
        row["company_name"] = row["company_name"][:NAME_LIMIT]
        row["symbol"] = row["symbol"][:SYMBOL_LIMIT]

    return list(stocks.values())


def main() -> None:

    """Build stocks.csv, or with --limit only print a small sample without writing anything."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    run_date = args.date or latest_source_date()
    rows = build(source_dir(run_date), args.limit)

    preview("stocks", rows, 12 if args.limit else 5)

    if args.limit:
        print("\nTest run with --limit, nothing written.")
        return

    target = clean_dir(run_date) / "stocks.csv"
    write_csv(target, COLUMNS, rows)

    with_sector = sum(1 for row in rows if row["sector"])
    with_price = sum(1 for row in rows if row["last_price"])
    etfs = sum(1 for row in rows if row["is_etf"] == "true")
    by_exchange = {name: sum(1 for row in rows if row["exchange"] == name) for name in ("nse", "bse")}

    print(f"\nWrote {target}")
    print(f"   exchange: {by_exchange}, etfs: {etfs}, with sector: {with_sector}, with price: {with_price}")


if __name__ == "__main__":
    main()
