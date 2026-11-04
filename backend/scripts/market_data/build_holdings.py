"""Read every downloaded AMC monthly portfolio Excel into one clean fund_holdings.csv."""

import argparse
import os
import re
from collections.abc import Iterator
from datetime import date, datetime
from difflib import SequenceMatcher
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
    "amc_name",
    "scheme_name",
    "base_scheme_name",
    "as_of_date",
    "holding_isin",
    "holding_name",
    "industry",
    "sector",
    "asset_class",
    "quantity",
    "market_value_lakhs",
    "weight_pct",
    ]

AMC_NAME_BY_FOLDER = {
    "sbi": "SBI",
    "icici": "ICICI Prudential",
    "hdfc": "HDFC",
    "nippon": "Nippon",
    "kotak": "Kotak",
    "absl": "Aditya Birla",
    "uti": "UTI",
    "axis": "Axis",
    "mirae": "Mirae",
    "dsp": "DSP",
    "tata": "Tata",
    "bandhan": "Bandhan",
    "motilal": "Motilal",
    "hsbc": "HSBC",
    "ppfas": "PPFAS",
    }

SECTOR_RULES = (
    ("bank", "financial_services"),
    ("financ", "financial_services"),
    ("insurance", "financial_services"),
    ("capital market", "financial_services"),
    ("fintech", "financial_services"),
    ("it -", "information_technology"),
    ("it-", "information_technology"),
    ("software", "information_technology"),
    ("information technology", "information_technology"),
    ("petroleum", "oil_gas_energy"),
    ("oil", "oil_gas_energy"),
    ("gas", "oil_gas_energy"),
    ("consumable fuel", "oil_gas_energy"),
    ("fmcg", "fmcg"),
    ("food", "fmcg"),
    ("beverage", "fmcg"),
    ("personal product", "fmcg"),
    ("household", "fmcg"),
    ("cigarette", "fmcg"),
    ("auto", "automobile"),
    ("pharma", "healthcare"),
    ("health", "healthcare"),
    ("hospital", "healthcare"),
    ("ferrous", "metals_mining"),
    ("metal", "metals_mining"),
    ("mining", "metals_mining"),
    ("minerals", "metals_mining"),
    ("aerospace", "capital_goods"),
    ("defen", "capital_goods"),
    ("electrical equipment", "capital_goods"),
    ("industrial", "capital_goods"),
    ("capital goods", "capital_goods"),
    ("commercial & construction vehicles", "capital_goods"),
    ("cement", "construction"),
    ("construction", "construction"),
    ("consumer durable", "consumer_durables"),
    ("retail", "consumer_services"),
    ("leisure", "consumer_services"),
    ("consumer services", "consumer_services"),
    ("telecom", "telecom"),
    ("power", "power"),
    ("realty", "realty"),
    ("real estate", "realty"),
    ("chemical", "chemicals"),
    ("fertili", "chemicals"),
    ("agrochemical", "chemicals"),
    ("textile", "textiles"),
    ("media", "media"),
    ("entertainment", "media"),
    ("transport", "services"),
    ("commercial services", "services"),
    ("services", "services"),
    ("diversified", "diversified"),
    )

CASH_WORDS = ("treps", "trp_", "tri-party", "triparty", "reverse repo", "net receivable", "net current asset", "cash", "margin")

TITLE_SKIP_WORDS = (
    "portfolio statement",
    "monthly portfolio",
    "portfolio as on",
    "portfolio as of",
    "statement as on",
    "half yearly",
    "back to index",
    "portfolio disclosure",
    "asset management",
    "registered office",
    "cin:",
    )

YIELD_WORDS = ("yield", "ytm", "ytc", "coupon")

BLOCK_START_WORD = "STARTS"

BLOCK_END_WORD = "ENDS"

ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

MONTH_DATE_PATTERNS = (
    (re.compile(r"([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})"), "{1} {0} {2}", "%d %B %Y"),
    (re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-]+([A-Za-z]+)[\s\-,]+(\d{4})"), "{0} {1} {2}", "%d %B %Y"),
    (re.compile(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})"), "{0} {1} {2}", "%d %m %Y"),
    (re.compile(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{2})\b"), "{0} {1} {2}", "%d %m %y"),
    )

UNIT_TRUST_CODES = {"25", "26"}

NAME_WORDS_DROPPED = {"fund", "scheme", "the", "plan", "an", "a", "of", "mutual", "mf"}

MATCH_THRESHOLD = 0.86

NAME_LIMIT = 255

INDUSTRY_LIMIT = 100


def read_workbook(path: Path) -> Iterator[tuple[str, list[list]]]:

    """Yield each sheet's name and rows from an .xlsx or .xls file."""

    with path.open("rb") as handle:
        is_old_excel = handle.read(2) != b"PK"

    if is_old_excel:

        import xlrd

        with open(os.devnull, "w") as quiet:
            book = xlrd.open_workbook(str(path), logfile=quiet)

        for sheet in book.sheets():
            rows = [sheet.row_values(index) for index in range(sheet.nrows)]

            yield sheet.name, rows

        return

    with path.open("rb") as handle:
        book = openpyxl.load_workbook(handle, read_only=True, data_only=True)

        for sheet in book.worksheets:

            yield sheet.title, [list(row) for row in sheet.iter_rows(values_only=True)]


def split_blocks(rows: list[list]) -> list[list[list]]:

    """Split a sheet that stacks many schemes between STARTS and ENDS marker rows, else return it whole."""

    first_cells = [text(row[0]) if row else "" for row in rows]

    if not any(cell.endswith(BLOCK_START_WORD) for cell in first_cells):
        return [rows]

    blocks: list[list[list]] = []
    current: list[list] | None = None

    for row, first in zip(rows, first_cells):

        if first.endswith(BLOCK_START_WORD):
            current = []
            continue

        if first.endswith(BLOCK_END_WORD):

            if current:
                blocks.append(current)

            current = None
            continue

        if current is not None:
            current.append(row)

    return blocks


def text(cell: object) -> str:

    """A cell as clean single-line text."""

    if cell is None:
        return ""

    return re.sub(r"\s+", " ", str(cell)).strip()


def number(cell: object) -> float | None:

    """A cell as a number, or None when it is blank or not numeric."""

    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return float(cell)

    cleaned = text(cell).replace(",", "").replace("%", "")

    try:
        return float(cleaned)

    except ValueError:
        return None


def parse_date(value: object) -> date | None:

    """Find a date inside a cell, whether it is a real date or text like 'as on September 30, 2026'."""

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    content = text(value)

    for pattern, layout, fmt in MONTH_DATE_PATTERNS:

        for match in pattern.finditer(content):
            candidate = layout.format(*match.groups())

            for attempt in (fmt, fmt.replace("%B", "%b")):

                try:
                    return datetime.strptime(candidate, attempt).date()

                except ValueError:
                    continue

    return None


def find_header(rows: list[list]) -> int | None:

    """Index of the first row that has both an ISIN column and a percent-of-assets column."""

    for index, row in enumerate(rows[:60]):
        cells = [text(cell).lower() for cell in row]

        has_isin = any("isin" in cell for cell in cells)
        has_weight = any("%" in cell or "net asset" in cell or "to nav" in cell for cell in cells)

        if has_isin and has_weight:
            return index

    return None


def column_map(header: list) -> dict[str, int]:

    """Locate the name, ISIN, industry, quantity, value and weight columns by their header words."""

    found: dict[str, int] = {}

    for index, cell in enumerate(header):
        label = text(cell).lower()

        if not label:
            continue

        if "isin" in label:
            found.setdefault("isin", index)

        elif any(word in label for word in YIELD_WORDS):
            continue

        elif "%" in label or "net asset" in label or "to nav" in label:
            found.setdefault("weight", index)

        elif "industry" in label or "rating" in label or "sector" in label:
            found.setdefault("industry", index)

        elif "quantity" in label or "no. of shares" in label or "units" in label:
            found.setdefault("quantity", index)

        elif "market" in label or "value" in label or "mkt val" in label:
            found.setdefault("value", index)

        elif "name" in label or "instrument" in label or "issuer" in label or "company" in label or "security" in label:
            found.setdefault("name", index)

    return found


def scheme_title(
    rows: list[list],
    header_at: int,
    sheet_name: str
    ) -> str:

    """The scheme name from the lines above the header, falling back to the sheet name."""

    for row in rows[:header_at]:

        lines = [line for cell in row for line in str(cell or "").splitlines()]

        for line in lines:
            label = re.sub(r"^(scheme\s*(name)?\s*:|portfolio of)\s*", "", text(line), flags=re.IGNORECASE)
            label = re.sub(r"\s+as on\s+\S+$", "", label, flags=re.IGNORECASE)

            if len(label) < 6 or " " not in label or label.endswith(":") or label.startswith("("):
                continue

            if label.lower().endswith("mutual fund") or any(word in label.lower() for word in TITLE_SKIP_WORDS):
                continue

            if parse_date(label) and len(label) < 40:
                continue

            return re.sub(r"\s*\(.*$", "", label).strip()

    return sheet_name.strip()


def sheet_date(
    rows: list[list],
    header_at: int
    ) -> date | None:

    """The as-of date above the header, preferring a line that says 'as on' or 'as of'."""

    cells = [cell for row in rows[:header_at + 1] for cell in row if cell is not None]
    labelled = [cell for cell in cells if re.search(r"\bas (on|of)\b", text(cell), flags=re.IGNORECASE)]

    for cell in [*labelled, *cells]:
        found = parse_date(cell)

        if found and found.year >= 2020:
            return found

    return None


def asset_class_for(
    isin: str,
    name: str,
    industry: str
    ) -> str:

    """Equity, debt, fund units or cash, judged from the ISIN shape."""

    if not isin:
        return "cash_and_other"

    if isin.startswith("INF"):
        return "fund_units"

    if isin.startswith("INE") and isin[7:9] == "01":
        return "equity"

    if isin.startswith("INE") and isin[7:9] in UNIT_TRUST_CODES:
        return "fund_units"

    if isin.startswith("IN"):
        return "debt"

    return "equity" if industry and "rating" not in industry.lower() else "cash_and_other"


def sector_for(industry: str) -> str:

    """Map an AMFI industry label to our stock_sector enum, using the first matching rule."""

    label = industry.lower()

    for words, sector in SECTOR_RULES:

        if words in label:
            return sector

    return "other"


def holding_name(
    row: list,
    columns: dict[str, int]
    ) -> str:

    """The instrument name, taking the nearest text cell left of the ISIN when the name column is empty."""

    name = text(row[columns["name"]]) if "name" in columns and columns["name"] < len(row) else ""

    if name:
        return re.sub(r"^[A-Z]{2,5} - ", "", name)

    for cell in reversed(row[:columns["isin"]]):
        label = text(cell)

        if len(label) > 6 and not re.fullmatch(r"[A-Z0-9]+", label):
            return label

    return ""


def cell_at(
    row: list,
    columns: dict[str, int],
    key: str
    ) -> object:

    """The cell for one mapped column, or None when the column or cell is missing."""

    index = columns.get(key)

    if index is None or index >= len(row):
        return None

    return row[index]


def parse_sheet(
    sheet_name: str,
    rows: list[list]
    ) -> tuple[str, date | None, list[dict]] | None:

    """Return the scheme title, as-of date and holding rows for one sheet, or None when it is not a portfolio."""

    header_at = find_header(rows)

    if header_at is None:
        return None

    columns = column_map(rows[header_at])

    if "isin" not in columns or "weight" not in columns:
        return None

    holdings = []

    for row in rows[header_at + 1:]:
        isin = text(cell_at(row, columns, "isin")).upper()
        weight = number(cell_at(row, columns, "weight"))
        name = holding_name(row, columns)

        if "grand total" in name.lower() or any("grand total" in text(cell).lower() for cell in row[:3]):
            break

        if weight is None or not name or "total" in name.lower():
            continue

        if not ISIN_PATTERN.match(isin):
            isin = ""

            if not any(word in name.lower() for word in CASH_WORDS):
                continue

        industry = text(cell_at(row, columns, "industry"))

        holdings.append({
            "holding_isin": isin,
            "holding_name": name[:NAME_LIMIT],
            "industry": industry[:INDUSTRY_LIMIT],
            "quantity": number(cell_at(row, columns, "quantity")),
            "market_value_lakhs": number(cell_at(row, columns, "value")),
            "weight": weight,
            })

    if not holdings:
        return None

    total = sum(row["weight"] for row in holdings)
    scale = 100 if total <= 1.5 else 1

    for row in holdings:
        row["weight_pct"] = round(row.pop("weight") * scale, 4)

    return scheme_title(rows, header_at, sheet_name), sheet_date(rows, header_at), holdings


def normalise(name: str) -> str:

    """Lowercase a scheme name and drop filler words so two spellings of one scheme compare equal."""

    name = re.sub(r"\(.*?\)", " ", name.lower()).replace("&", " and ")
    name = re.sub(r"fund\s+of\s+funds?", " fof ", name)
    name = re.sub(r"exchange\s+traded\s+fund", " etf ", name)
    words = re.findall(r"[a-z0-9]+", name)

    return " ".join(word for word in words if word not in NAME_WORDS_DROPPED)


def scheme_matcher(funds: list[dict]):

    """Build a function that maps a portfolio title to the AMFI base scheme name of the same AMC."""

    by_amc: dict[str, dict[str, str]] = {}

    for fund in funds:
        by_amc.setdefault(fund["amc_name"], {})[normalise(fund["base_scheme_name"])] = fund["base_scheme_name"]

    def match(
        amc_name: str,
        title: str
        ) -> str:

        """Exact normalised match first, then the closest name above the similarity threshold."""

        key = normalise(title)
        kind = {"etf", "fof"} & set(key.split())
        numbers = set(re.findall(r"\d+", key))
        candidates = {
            name_key: base_name
            for name_key, base_name in by_amc.get(amc_name, {}).items()
            if {"etf", "fof"} & set(name_key.split()) == kind and set(re.findall(r"\d+", name_key)) == numbers
            }

        if key in candidates:
            return candidates[key]

        best, best_score = "", 0.0

        for candidate_key, base_name in candidates.items():
            score = SequenceMatcher(None, key, candidate_key).ratio()

            if score > best_score:
                best, best_score = base_name, score

        return best if best_score >= MATCH_THRESHOLD else ""

    return match


def amc_full_name(
    folder_name: str,
    amc_names: set[str]
    ) -> str:

    """The AMFI AMC name for a download folder, such as ppfas to PPFAS Asset Management Pvt. Ltd."""

    hint = AMC_NAME_BY_FOLDER.get(folder_name, folder_name).lower()

    for name in sorted(amc_names):

        if name.lower().startswith(hint):
            return name

    return AMC_NAME_BY_FOLDER.get(folder_name, folder_name)


def build(
    folder: Path,
    clean_folder: Path,
    amc_filter: str | None,
    limit: int | None
    ) -> tuple[list[dict], list[str]]:

    """Parse every portfolio file under the sources folder and return holding rows plus a list of problems."""

    funds = read_csv(clean_folder / "mutual_funds.csv")
    stock_sectors = {row["isin"]: row["sector"] for row in read_csv(clean_folder / "stocks.csv") if row["sector"]}
    match = scheme_matcher(funds)
    amc_names = {fund["amc_name"] for fund in funds}

    rows: list[dict] = []
    problems: list[str] = []

    for amc_folder in sorted((folder / "portfolios").iterdir()):

        if not amc_folder.is_dir() or (amc_filter and amc_folder.name != amc_filter):
            continue

        amc_name = amc_full_name(amc_folder.name, amc_names)
        amc_rows: list[dict] = []
        files = sorted(path for path in amc_folder.iterdir() if path.suffix.lower() in (".xls", ".xlsx"))[:limit]

        for path in files:

            try:
                sheets = list(read_workbook(path))

            except Exception as exc:

                problems.append(f"{amc_folder.name}/{path.name}: cannot open ({exc})")

                continue

            blocks = [(sheet_name, block) for sheet_name, sheet_rows in sheets for block in split_blocks(sheet_rows)]

            for sheet_name, block_rows in blocks:
                parsed = parse_sheet(sheet_name, block_rows)

                if parsed is None:
                    continue

                title, as_of, holdings = parsed
                base_name = match(amc_name, title)

                if not base_name:
                    problems.append(f"{amc_folder.name}/{path.name}[{sheet_name}]: no AMFI match for '{title}'")

                if as_of is None:
                    problems.append(f"{amc_folder.name}/{path.name}[{sheet_name}]: no as-of date, skipped")

                    continue

                for holding in holdings:
                    asset_class = asset_class_for(holding["holding_isin"], holding["holding_name"], holding["industry"])
                    sector = ""

                    if asset_class == "equity":
                        sector = stock_sectors.get(holding["holding_isin"]) or sector_for(holding["industry"])

                    amc_rows.append({
                        "amc_name": amc_name,
                        "scheme_name": title[:NAME_LIMIT],
                        "base_scheme_name": base_name,
                        "as_of_date": as_of.isoformat(),
                        **holding,
                        "sector": sector,
                        "asset_class": asset_class,
                        })

        rows.extend(with_common_date(amc_rows))

    return rows, problems


def with_common_date(amc_rows: list[dict]) -> list[dict]:

    """Give every holding of one AMC the portfolio date most of its sheets carry, fixing sheets that picked a stray date."""

    if not amc_rows:
        return amc_rows

    dates: dict[str, int] = {}

    for row in amc_rows:
        dates[row["as_of_date"]] = dates.get(row["as_of_date"], 0) + 1

    common = max(dates, key=dates.get)

    for row in amc_rows:
        row["as_of_date"] = common

    return amc_rows


def main() -> None:

    """Build fund_holdings.csv, or with --limit read only a few files per AMC and print a sample."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--amc", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    run_date = args.date or latest_source_date()
    rows, problems = build(source_dir(run_date), clean_dir(run_date), args.amc, args.limit)

    preview("fund_holdings", rows, 8)

    schemes = {(row["amc_name"], row["scheme_name"]) for row in rows}
    matched = {(row["amc_name"], row["scheme_name"]) for row in rows if row["base_scheme_name"]}

    print(f"\nSchemes read: {len(schemes)}, matched to AMFI: {len(matched)}")

    for problem in problems[:40]:
        print("   PROBLEM", problem)

    if args.limit or args.amc:
        print("\nTest run with --limit or --amc, nothing written.")
        return

    target = clean_dir(run_date) / "fund_holdings.csv"
    write_csv(target, COLUMNS, rows)

    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
