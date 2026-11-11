"""Reading an uploaded spreadsheet or CSV into plain sheets of cells, each cell keeping its address for evidence."""

import csv
import io
from dataclasses import dataclass, field
from typing import Any

import openpyxl
import xlrd
from openpyxl.utils import get_column_letter


XLSX_SIGNATURE = b"PK\x03\x04"
XLS_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

MIME_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    }

CSV_ENCODINGS = ("utf-8-sig", "cp1252")
CSV_DELIMITERS = ",;\t|"
CSV_SNIFF_BYTES = 4096


class UnreadableFile(ValueError):

    """A file that is not the type its name says, or cannot be opened as one."""


@dataclass
class Cell:

    """One non-empty cell value and its address, such as D18."""

    value: Any
    ref: str


@dataclass
class Sheet:

    """One sheet of a workbook, or the whole of a CSV, as rows of cells, with row 1 first."""

    name: str
    rows: list[list[Cell | None]] = field(default_factory=list)
    hidden: bool = False

    def row_values(self, index: int) -> list[Any]:

        """The plain values of one row by its zero-based index, with None for blanks."""

        return [cell.value if cell else None for cell in self.rows[index]]


def file_kind(
    filename: str,
    data: bytes
    ) -> str:

    """The file's ending, checked against the bytes it starts with, so a renamed file is refused."""

    ending = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ending not in MIME_TYPES:
        raise UnreadableFile("Only .xlsx, .xls and .csv files can be imported")

    if ending == ".xlsx" and not data.startswith(XLSX_SIGNATURE):
        raise UnreadableFile("This file is named .xlsx but is not an Excel workbook")

    if ending == ".xls" and not data.startswith(XLS_SIGNATURE):
        raise UnreadableFile("This file is named .xls but is not an Excel workbook")

    if ending == ".csv" and (data.startswith(XLSX_SIGNATURE) or data.startswith(XLS_SIGNATURE) or b"\x00" in data[:CSV_SNIFF_BYTES]):
        raise UnreadableFile("This file is named .csv but is not a text file")

    return ending


def read_file(
    ending: str,
    data: bytes
    ) -> list[Sheet]:

    """Read the file into sheets by its checked ending."""

    try:

        if ending == ".xlsx":
            return read_xlsx(data)

        if ending == ".xls":
            return read_xls(data)

        return [read_csv(data)]

    except UnreadableFile:
        raise

    except Exception as exc:
        raise UnreadableFile("The file could not be opened. It may be damaged or password protected.") from exc


def read_xlsx(data: bytes) -> list[Sheet]:

    """Read every sheet of an .xlsx workbook using the values Excel last saved, not the formulas."""

    workbook = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    sheets = []

    for worksheet in workbook.worksheets:

        sheet = Sheet(name=worksheet.title, hidden=worksheet.sheet_state != "visible")

        for row in worksheet.iter_rows():
            sheet.rows.append([Cell(cell.value, cell.coordinate) if has_value(cell.value) else None for cell in row])

        sheets.append(sheet)

    return sheets


def read_xls(data: bytes) -> list[Sheet]:

    """Read every sheet of an old .xls workbook, turning Excel date cells into dates."""

    workbook = xlrd.open_workbook(file_contents=data)
    sheets = []

    for worksheet in workbook.sheets():

        sheet = Sheet(name=worksheet.name, hidden=worksheet.visibility != 0)

        for row_index in range(worksheet.nrows):

            row = []

            for column_index in range(worksheet.ncols):

                cell = worksheet.cell(row_index, column_index)
                value = cell.value

                if cell.ctype == xlrd.XL_CELL_DATE:
                    value = xlrd.xldate.xldate_as_datetime(value, workbook.datemode)

                ref = f"{get_column_letter(column_index + 1)}{row_index + 1}"
                row.append(Cell(value, ref) if has_value(value) else None)

            sheet.rows.append(row)

        sheets.append(sheet)

    return sheets


def read_csv(data: bytes) -> Sheet:

    """Read a CSV in UTF-8 or Windows encoding, finding its delimiter from the first few lines."""

    text = decode(data)

    try:
        dialect = csv.Sniffer().sniff(text[:CSV_SNIFF_BYTES], delimiters=CSV_DELIMITERS)

    except csv.Error:
        dialect = csv.excel

    sheet = Sheet(name="CSV")

    for row_index, values in enumerate(csv.reader(io.StringIO(text), dialect)):
        sheet.rows.append([
            Cell(value.strip(), f"{get_column_letter(column_index + 1)}{row_index + 1}") if has_value(value) else None
            for column_index, value in enumerate(values)
            ])

    return sheet


def decode(data: bytes) -> str:

    """Decode CSV bytes, trying UTF-8 first and Windows encoding second."""

    for encoding in CSV_ENCODINGS:

        try:
            return data.decode(encoding)

        except UnicodeDecodeError:
            continue

    raise UnreadableFile("The CSV text encoding is not supported")


def has_value(value: Any) -> bool:

    """Whether a raw cell holds anything, treating blank text as empty."""

    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    return True
