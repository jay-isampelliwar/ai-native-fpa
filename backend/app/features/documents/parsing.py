"""The shapes every parser returns, and the helpers they share to find headers and read cells into fields."""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from app.features.documents.fields import amount_fields, field_kind, read_value
from app.features.documents.normalize import NotReadable, header_key, is_empty, to_decimal
from app.features.documents.reader import Cell, Sheet
from app.features.documents.totals import is_summary_line


HEADER_SEARCH_ROWS = 25

MAX_HEADER_DIGITS = 3

DIGITS = re.compile(r"\d")


@dataclass
class ParsedRow:

    """One full record read from a file, with the cells it came from and the problems found while reading."""

    target_table: str
    data: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    parent: "ParsedRow | None" = None


@dataclass
class SheetNote:

    """What happened to one sheet: imported, empty, skipped, hidden, or waiting for a mapping."""

    sheet: str
    outcome: str
    message: str
    rows: int = 0

    def as_dict(self) -> dict[str, Any]:

        """The note as plain JSON for the document summary."""

        return {"sheet": self.sheet, "outcome": self.outcome, "message": self.message, "rows": self.rows}


@dataclass
class ParseResult:

    """Everything a parser found in one file."""

    rows: list[ParsedRow] = field(default_factory=list)
    notes: list[SheetNote] = field(default_factory=list)
    printed: list[dict[str, Any]] = field(default_factory=list)


class RowBuilder:

    """Builds one ParsedRow cell by cell, cleaning each value and recording where it came from."""

    def __init__(
        self,
        table: str,
        sheet: Sheet,
        row_number: int
        ) -> None:

        """Start an empty row for one table from one sheet row."""

        self.row = ParsedRow(target_table=table, source={"sheet": sheet.name, "row": row_number, "cells": {}})

    def put(
        self,
        field_name: str,
        cell: Cell | None
        ) -> None:

        """Clean one cell into a field, keeping an error instead of a value when it cannot be read."""

        if cell is None or is_empty(cell.value):
            return

        self.row.source["cells"][field_name] = cell.ref

        try:
            self.row.data[field_name] = read_value(field_kind(self.row.target_table, field_name), cell.value)

        except NotReadable as exc:
            self.row.errors.append(f"{field_name}: '{cell.value}' in {cell.ref} {exc}")

    def set(
        self,
        field_name: str,
        value: Any
        ) -> None:

        """Set a field from a value the parser already knows, such as a frequency stated in a sheet title."""

        if value is not None:
            self.row.data[field_name] = value

    def warn(self, message: str) -> None:

        """Add a warning the user should look at."""

        self.row.warnings.append(message)

    def has_content(self) -> bool:

        """Whether the row holds a real record, not a template line with every amount blank or zero."""

        amounts = amount_fields(self.row.target_table)

        if not amounts:
            return bool(self.row.data) or bool(self.row.errors)

        for name in amounts:

            value = self.row.data.get(name)

            if value is not None and to_decimal(value) != 0:
                return True

        return any(error.split(":")[0] in amounts for error in self.row.errors)


def find_header(
    sheet: Sheet,
    needed: set[str]
    ) -> int | None:

    """The zero-based index of the first row holding every needed header, looking only near the top."""

    for index in range(min(len(sheet.rows), HEADER_SEARCH_ROWS)):

        keys = {header_key(value) for value in sheet.row_values(index) if value is not None}

        if needed <= keys:
            return index

    return None


def looks_like_header(values: list[Any]) -> bool:

    """Two or more text cells, none holding a number, date or an id with several digits, such as a PAN or phone."""

    if len(values) < 2:
        return False

    return all(isinstance(value, str) and len(DIGITS.findall(value)) < MAX_HEADER_DIGITS for value in values)


def guess_header(sheet: Sheet) -> int | None:

    """The zero-based index of the widest header-like row near the top, preferring one with data right under it."""

    best = None
    best_score = (0, False)
    limit = min(len(sheet.rows), HEADER_SEARCH_ROWS)

    for index in range(limit):

        values = [value for value in sheet.row_values(index) if value is not None]

        if not looks_like_header(values):
            continue

        score = (len(values), has_data_below(sheet, index))

        if score > best_score:
            best, best_score = index, score

    return best


def has_data_below(
    sheet: Sheet,
    index: int
    ) -> bool:

    """Whether the next non-blank row under this one holds a number, a date or digits, as a data row does."""

    for below in range(index + 1, len(sheet.rows)):

        values = [value for value in sheet.row_values(below) if value is not None]

        if values:
            return any(not isinstance(value, str) or DIGITS.search(value) for value in values)

    return False


def header_columns(
    sheet: Sheet,
    header_index: int
    ) -> dict[str, int]:

    """Map each header's tidied text to its column position."""

    columns = {}

    for position, value in enumerate(sheet.row_values(header_index)):

        if value is not None:
            columns.setdefault(header_key(value), position)

    return columns


def data_rows(
    sheet: Sheet,
    header_index: int
    ) -> Iterator[tuple[int, dict[str, Cell | None]]]:

    """Yield each non-blank row under the header as its sheet row number and a header-to-cell map, leaving out total lines."""

    columns = header_columns(sheet, header_index)

    for index in range(header_index + 1, len(sheet.rows)):

        row = sheet.rows[index]

        if not any(row) or is_summary_line(row):
            continue

        cells = {key: row[position] if position < len(row) else None for key, position in columns.items()}

        yield index + 1, cells


def first_text(cells: dict[str, Cell | None]) -> str:

    """The first text value in a row, used to spot notes like 'Status: Not held' in place of data."""

    for cell in cells.values():

        if cell is not None:
            return str(cell.value)

    return ""
