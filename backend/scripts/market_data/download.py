"""Download the raw NSE, BSE and AMFI files for one run date into sql/data/sources/<date>/."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import httpx

from scripts.market_data.common import source_dir

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

TIMEOUT_SECONDS = 120

MAX_PARALLEL = 4

PRICE_LOOKBACK_DAYS = 7

DEFAULT_MARKET_CAP_FILE = "AverageMarketCapitalization31Dec2025.xlsx"

FIXED_FILES = {
    "nse/EQUITY_L.csv": "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    "nse/SME_EQUITY_L.csv": "https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv",
    "nse/eq_etfseclist.csv": "https://nsearchives.nseindia.com/content/equities/eq_etfseclist.csv",
    "nse/ind_nifty500list.csv": "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    "nse/ind_niftytotalmarket_list.csv": "https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv",
    "nse/ind_niftymicrocap250_list.csv": "https://nsearchives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
    "amfi/NAVAll.txt": "https://portal.amfiindia.com/spages/NAVAll.txt",
    "amfi/SchemeData.csv": "https://portal.amfiindia.com/DownloadSchemeData_Po.aspx?mf=0",
    }


def fetch(url: str) -> bytes | None:

    """Return the body of one GET, or None when the server says it is not there."""

    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
        )

    if response.status_code in (403, 404):
        return None

    response.raise_for_status()

    return response.content


def save(
    target: Path,
    url: str
    ) -> str:

    """Download one URL to a file and return a one-line report."""

    body = fetch(url)

    if body is None:
        return f"MISSING  {target.name}  {url}"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)

    return f"OK  {len(body):>9} bytes  {target.relative_to(target.parents[2])}"


def save_latest_prices(
    folder: Path,
    run_date: date
    ) -> list[str]:

    """Walk back from the day before run_date to the newest trading day with NSE and BSE price files."""

    for back in range(1, PRICE_LOOKBACK_DAYS + 1):
        day = run_date - timedelta(days=back)

        nse_url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{day:%d%m%Y}.csv"
        nse_body = fetch(nse_url)

        if nse_body is None:
            continue

        nse_target = folder / "nse" / f"sec_bhavdata_full_{day:%d%m%Y}.csv"
        nse_target.parent.mkdir(parents=True, exist_ok=True)
        nse_target.write_bytes(nse_body)

        bse_url = f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{day:%Y%m%d}_F_0000.CSV"
        bse_report = save(folder / "bse" / f"BhavCopy_BSE_CM_{day:%Y%m%d}.csv", bse_url)

        return [f"OK  prices for {day.isoformat()}", bse_report]

    return [f"MISSING  no NSE price file in the {PRICE_LOOKBACK_DAYS} days before {run_date}"]


def main() -> None:

    """Download every source file, a few at a time, and print what landed."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--market-cap-file", default=DEFAULT_MARKET_CAP_FILE)
    args = parser.parse_args()

    folder = source_dir(args.date)

    files = dict(FIXED_FILES)
    files[f"amfi/{args.market_cap_file}"] = f"https://www.amfiindia.com/Themes/Theme1/downloads/{args.market_cap_file}"

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        reports = list(pool.map(lambda item: save(folder / item[0], item[1]), files.items()))

    reports.extend(save_latest_prices(folder, args.date))

    print(f"Sources folder: {folder}")

    for report in reports:
        print("  ", report)


if __name__ == "__main__":
    main()
