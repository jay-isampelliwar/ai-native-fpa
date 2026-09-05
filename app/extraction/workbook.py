"""Reading the shape of a spreadsheet: which sheet holds the table, where its header is, and what it is.

Real statements do not start at A1. One of the three formats this was built against puts its header
on row 23 of column B, another on row 21 after a block of personal details, and a third on row 1.
Assuming a header position is the fastest way to import a statement's summary block as holdings, so
the header is found rather than assumed.

A header row is scored, not matched. The row that looks most like a header is the one with several
short text cells that is followed by rows containing numbers, which is true of every tabular export
and false of a title, a summary pair or a name and address block. Scoring means an unfamiliar layout
degrades to a lower confidence rather than to a wrong answer.

The fingerprint is what turns an unknown file into a known one exactly once. It hashes the sheet
names and the normalised header cells - not the data, not the filename, not the dates - so the same
export from the same provider next month fingerprints identically while a different provider's file
does not.

``sample_rows`` deliberately returns only a few data rows and only from below the header. Anything
above the header may be personal details: one of the three formats carries a name, a mobile number
and a PAN in rows four to six, and those must never reach a mapping prompt, a log line or a model.

Nothing here interprets a column's meaning. This module says where the table is; deciding that
"Qty Available" means quantity is the adapter's or the mapping's job.
"""

import hashlib
import re
from io import BytesIO

from openpyxl import load_workbook
from pydantic import BaseModel, Field

from app.extraction.values import clean_text

MAXIMUM_HEADER_SCAN_ROWS = 40
SAMPLE_ROW_COUNT = 3
MINIMUM_HEADER_CELLS = 3

PII_HEADERS = frozenset({"pan", "mobile", "mobile number", "phone", "email", "aadhaar", "aadhar", "name", "address"})


class SheetProfile(BaseModel):

    """Where one sheet's table starts and what its columns are called, without saying what they mean."""

    name: str
    header_row: int | None = None
    first_data_row: int | None = None
    first_column: int = 1
    headers: list[str] = Field(default_factory=list)
    sample_rows: list[list[str]] = Field(default_factory=list)
    data_row_count: int = 0


class WorkbookProfile(BaseModel):

    """The shape of a whole workbook, and the fingerprint that recognises this layout again."""

    sheet_names: list[str] = Field(default_factory=list)
    sheets: list[SheetProfile] = Field(default_factory=list)
    fingerprint: str = ""


def normalise_header(text: str) -> str:

    """Reduce a heading to a comparable key, since providers differ on case, symbols and spacing."""

    lowered = clean_text(text).lower()

    lowered = re.sub(r"\(.*?\)", " ", lowered)

    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)

    return " ".join(lowered.split())


def is_header_like(cell: object) -> bool:

    """Judge whether one cell reads as a column heading rather than as data."""

    text = clean_text(cell)

    if not text or len(text) > 60:
        return False

    return not text.replace(".", "").replace("-", "").replace(",", "").isdigit()


def score_header_row(cells: list[object], following: list[list[object]]) -> int:

    """Score a candidate header by its own shape and by whether numbers follow it."""

    header_cells = [cell for cell in cells if is_header_like(cell)]

    if len(header_cells) < MINIMUM_HEADER_CELLS:
        return 0

    numeric_below = 0

    for row in following:

        for cell in row:

            text = clean_text(cell)

            if text and any(character.isdigit() for character in text):
                numeric_below += 1
                break

    return len(header_cells) * 2 + numeric_below


def profile_sheet(name: str, rows: list[list[object]]) -> SheetProfile:

    """Find the header row of one sheet and sample a few data rows from beneath it."""

    best_row = None
    best_score = 0

    for index in range(min(len(rows), MAXIMUM_HEADER_SCAN_ROWS)):

        score = score_header_row(rows[index], rows[index + 1 : index + 4])

        if score > best_score:
            best_score = score
            best_row = index

    if best_row is None:
        return SheetProfile(name=name)

    header_cells = rows[best_row]

    first_column = next((position for position, cell in enumerate(header_cells) if clean_text(cell)), 0)

    headers = [clean_text(cell) for cell in header_cells[first_column:]]

    data_rows = [row for row in rows[best_row + 1 :] if any(clean_text(cell) for cell in row)]

    first_data_row = None

    for offset, row in enumerate(rows[best_row + 1 :], start=best_row + 2):

        if any(clean_text(cell) for cell in row):
            first_data_row = offset
            break

    return SheetProfile(
        name=name,
        header_row=best_row + 1,
        first_data_row=first_data_row,
        first_column=first_column + 1,
        headers=headers,
        sample_rows=[[clean_text(cell) for cell in row[first_column:]] for row in data_rows[:SAMPLE_ROW_COUNT]],
        data_row_count=len(data_rows),
    )


def read_sheets(content: bytes) -> dict[str, list[list[object]]]:

    """Load every sheet's cells with formulas already evaluated, since a total row is often a formula."""

    workbook = load_workbook(BytesIO(content), data_only=True, read_only=True)

    sheets = {}

    for worksheet in workbook.worksheets:
        sheets[worksheet.title] = [list(row) for row in worksheet.iter_rows(values_only=True)]

    workbook.close()

    return sheets


def profile_workbook(content: bytes) -> WorkbookProfile:

    """Describe a workbook's tables and compute the fingerprint that recognises this layout again."""

    sheets = read_sheets(content)

    profiles = [profile_sheet(name, rows) for name, rows in sheets.items()]

    return WorkbookProfile(
        sheet_names=list(sheets),
        sheets=profiles,
        fingerprint=fingerprint_of(profiles, list(sheets)),
    )


def fingerprint_of(profiles: list[SheetProfile], sheet_names: list[str]) -> str:

    """Hash the layout rather than the data, so next month's export of the same shape matches."""

    parts = ["|".join(sorted(normalise_header(name) for name in sheet_names))]

    for profile in sorted(profiles, key=lambda item: item.name):

        headers = "|".join(normalise_header(header) for header in profile.headers if clean_text(header))

        parts.append(f"{normalise_header(profile.name)}::{headers}")

    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:32]


def carries_personal_details(profile: SheetProfile) -> bool:

    """Report whether a detected table is actually a personal details block rather than holdings."""

    return bool({normalise_header(header) for header in profile.headers} & PII_HEADERS)
