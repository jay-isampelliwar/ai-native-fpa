"""Shared paths and CSV helpers for the market data scripts."""

import csv
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

DATA_ROOT = REPO_ROOT / "sql" / "data"

SOURCES_ROOT = DATA_ROOT / "sources"

CLEAN_ROOT = DATA_ROOT / "clean"


def source_dir(run_date: date) -> Path:

    """Folder that holds the raw downloaded files for one run date."""

    return SOURCES_ROOT / run_date.isoformat()


def clean_dir(run_date: date) -> Path:

    """Folder that holds the cleaned, ready-to-load CSV files for one run date."""

    return CLEAN_ROOT / run_date.isoformat()


def latest_source_date() -> date:

    """Newest run date that has a downloaded sources folder."""

    dates = sorted(path.name for path in SOURCES_ROOT.iterdir() if path.is_dir())

    if not dates:
        raise SystemExit(f"No downloaded sources in {SOURCES_ROOT}, run download first")

    return date.fromisoformat(dates[-1])


def read_csv(path: Path) -> list[dict[str, str]]:

    """Read a CSV into dicts, trimming spaces from every header and value."""

    with path.open(encoding="utf-8-sig", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        header = [name.strip() for name in next(reader)]

        return [
            {name: value.strip() for name, value in zip(header, row) if name}
            for row in reader
            if any(cell.strip() for cell in row)
            ]


def write_csv(
    path: Path,
    columns: list[str],
    rows: list[dict]
    ) -> None:

    """Write rows to a CSV with a fixed column order, creating the folder if needed."""

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def preview(
    title: str,
    rows: list[dict],
    count: int
    ) -> None:

    """Print the first few rows so a test run can be checked by eye."""

    print(f"\n{title}: {len(rows)} rows")

    for row in rows[:count]:
        print("  ", row)
