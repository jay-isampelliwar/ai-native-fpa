"""Reading an uploaded spreadsheet, CSV, PDF or photo into sheets of cells for code, and pages for the model, each keeping its address."""

import csv
import io
from dataclasses import dataclass, field
from typing import Any

import openpyxl
import pdfplumber
import xlrd
from openpyxl.utils import get_column_letter
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException


XLSX_SIGNATURE = b"PK\x03\x04"
XLS_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
PDF_SIGNATURE = b"%PDF"
PNG_SIGNATURE = b"\x89PNG"
JPEG_SIGNATURE = b"\xff\xd8\xff"

MIME_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    }

IMAGE_ENDINGS = {".png", ".jpg", ".jpeg", ".webp"}

MAX_PDF_PAGES = 20
MIN_PAGE_TEXT = 40
PAGE_RENDER_DPI = 150

CSV_ENCODINGS = ("utf-8-sig", "cp1252")
CSV_DELIMITERS = ",;\t|"
CSV_SNIFF_BYTES = 4096


class UnreadableFile(ValueError):

    """A file that is not the type its name says, or cannot be opened as one."""


class PasswordNeeded(ValueError):

    """A locked PDF, opened with no password or a wrong one."""


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


@dataclass
class Page:

    """One page only the model can read: its text when it has text but no table, or a picture of it when scanned."""

    number: int
    text: str | None = None
    image: bytes | None = None
    mime_type: str = "image/png"


@dataclass
class FileContent:

    """Everything read from one file: tables as sheets for code to read, and pages left for the model."""

    sheets: list[Sheet] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)


SIGNATURES = {
    ".pdf": (PDF_SIGNATURE,),
    ".png": (PNG_SIGNATURE,),
    ".jpg": (JPEG_SIGNATURE,),
    ".jpeg": (JPEG_SIGNATURE,),
    }


def file_kind(
    filename: str,
    data: bytes
    ) -> str:

    """The file's ending, checked against the bytes it starts with, so a renamed file is refused."""

    ending = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ending not in MIME_TYPES:
        raise UnreadableFile("Only spreadsheets, CSV files, PDFs and photos (.png, .jpg, .webp) can be imported")

    if ending in SIGNATURES and not data.startswith(SIGNATURES[ending]):
        raise UnreadableFile(f"This file is named {ending} but its contents are not")

    if ending == ".webp" and not (data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
        raise UnreadableFile("This file is named .webp but its contents are not")

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


def read_document(
    ending: str,
    data: bytes,
    password: str | None = None
    ) -> FileContent:

    """Read any accepted file: spreadsheets and CSVs into sheets, PDFs into table sheets and pages, photos into one page."""

    if ending in IMAGE_ENDINGS:
        return FileContent(pages=[Page(number=1, image=data, mime_type=MIME_TYPES[ending])])

    if ending == ".pdf":
        return read_pdf(data, password)

    return FileContent(sheets=read_file(ending, data))


def read_pdf(
    data: bytes,
    password: str | None
    ) -> FileContent:

    """Read each page's tables as sheets; a page with no table gives its text, or a picture when it has no text."""

    try:
        pdf = pdfplumber.open(io.BytesIO(data), password=password or "")

    except PdfminerException as exc:

        if is_locked(exc):
            raise PasswordNeeded("This PDF is locked. Give its password to read it.") from exc

        raise UnreadableFile("The PDF could not be opened. It may be damaged.") from exc

    with pdf:

        if len(pdf.pages) > MAX_PDF_PAGES:
            raise UnreadableFile(f"This PDF has {len(pdf.pages)} pages. Files of up to {MAX_PDF_PAGES} pages can be read.")

        content = FileContent()

        for number, page in enumerate(pdf.pages, start=1):

            tables = [table for table in page.extract_tables() if table and len(table) > 1]

            for index, table in enumerate(tables, start=1):
                content.sheets.append(table_sheet(f"Page {number} table {index}", table))

            if tables:
                continue

            text = (page.extract_text() or "").strip()

            if len(text) >= MIN_PAGE_TEXT:
                content.pages.append(Page(number=number, text=text))
                continue

            buffer = io.BytesIO()
            page.to_image(resolution=PAGE_RENDER_DPI).original.save(buffer, format="PNG")
            content.pages.append(Page(number=number, image=buffer.getvalue()))

        return content


def is_locked(exc: Exception) -> bool:

    """Whether pdfminer refused the file for a missing or wrong password."""

    cause = exc.args[0] if exc.args else exc

    return isinstance(cause, PDFPasswordIncorrect) or "password" in str(cause).lower()


def table_sheet(
    name: str,
    table: list[list[str | None]]
    ) -> Sheet:

    """One PDF table as a sheet, each cell's address naming the page table, row and column."""

    sheet = Sheet(name=name)

    for row_index, values in enumerate(table):
        sheet.rows.append([
            Cell(" ".join(value.split()), f"{name}, {get_column_letter(column_index + 1)}{row_index + 1}") if has_value(value) else None
            for column_index, value in enumerate(values)
            ])

    return sheet


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
