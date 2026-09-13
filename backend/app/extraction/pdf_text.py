"""Reading bank transactions from a PDF statement's own text layer, before any model is asked."""

import io
from decimal import Decimal

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect

from app.extraction.bank_csv import (
    AMOUNT_ALIASES,
    CREDIT_ALIASES,
    DATE_ALIASES,
    DEBIT_ALIASES,
    DESCRIPTION_ALIASES,
    find_column,
    guess_category,
    parse_amount,
    parse_date,
)
from app.extraction.base import ExtractedRow, ExtractionResult
from app.extraction.vision import extract_from_images, page_images

PDF_MAGIC = b"%PDF"

MINIMUM_TEXT_CHARACTERS = 200

MAXIMUM_ERROR_DEPTH = 8


def is_password_failure(error: BaseException | None) -> bool:

    """Recognise a password refusal wherever it was wrapped, since pdfplumber hides pdfminer's own error."""

    for _ in range(MAXIMUM_ERROR_DEPTH):

        if error is None:
            return False

        if isinstance(error, PDFPasswordIncorrect):
            return True

        error = error.__cause__ or error.__context__

    return False


def cells_as_text(cells: list) -> list[str]:

    """Flatten one extracted table row to plain strings, since a merged cell comes back as None."""

    return [str(cell or "").replace("\n", " ").strip() for cell in cells]


def header_index(table: list[list]) -> int | None:

    """Find which row of a table is its heading row, since a statement opens with a letterhead."""

    for index, cells in enumerate(table):

        headers = cells_as_text(cells)

        if find_column(headers, DATE_ALIASES) is None:
            continue

        if find_column(headers, DEBIT_ALIASES) or find_column(headers, AMOUNT_ALIASES):
            return index

    return None


def row_to_transaction(
    cells: list[str],
    headers: list[str],
    page_number: int,
    row_number: int,
    ) -> ExtractedRow | None:

    """Turn one table line into a staged transaction, skipping anything that is not a debit."""

    record = dict(zip(headers, cells, strict=False))

    credit_column = find_column(headers, CREDIT_ALIASES)

    if credit_column and parse_amount(record.get(credit_column, "")) is not None:
        return None

    debit_column = find_column(headers, DEBIT_ALIASES)
    amount_column = find_column(headers, AMOUNT_ALIASES)

    amount = parse_amount(record.get(debit_column, "")) if debit_column else None

    if amount is None and amount_column:
        amount = parse_amount(record.get(amount_column, ""))

    if amount is None:
        return None

    date_column = find_column(headers, DATE_ALIASES)

    occurred_on, date_issue = parse_date(record.get(date_column, "") if date_column else "")

    description_column = find_column(headers, DESCRIPTION_ALIASES)

    description = record.get(description_column, "").strip() if description_column else ""

    confidence = Decimal("0.950")

    if date_issue:
        confidence = Decimal("0.400")

    elif not description:
        confidence = Decimal("0.750")

    return ExtractedRow(
        target_table="expense_transactions",
        payload={
            "occurred_on": occurred_on,
            "amount": str(amount),
            "category": guess_category(description),
            "merchant": description[:160],
            "description": description[:500],
        },
        confidence=confidence,
        issue=date_issue,
        source_sheet=f"page {page_number}",
        source_row_number=row_number,
        source_cells=cells,
    )


class PdfTextExtractor:

    """Reads bank transactions from a PDF that carries a real text layer, never from a picture of one."""

    name = "pdf_text.v1"

    def can_handle(self, filename: str, content_type: str, head: bytes) -> bool:

        """Claim any PDF, leaving whether it actually holds readable text to the extraction itself."""

        if not head.startswith(PDF_MAGIC):
            return False

        return filename.lower().endswith(".pdf") or "pdf" in content_type

    async def extract(
        self,
        content: bytes,
        filename: str,
        user_id: int,
        password: str | None = None,
        ) -> ExtractionResult:

        """Read every debit line this PDF states in text, refusing a scan rather than guessing at it."""

        try:
            document = pdfplumber.open(io.BytesIO(content), password=password or "")

        except Exception as exc:

            if not is_password_failure(exc):
                return ExtractionResult(
                    extractor=self.name,
                    detected_format="pdf",
                    document_kind="unknown",
                    error=f"this PDF could not be opened: {type(exc).__name__}",
                )

            if password:
                return ExtractionResult(
                    extractor=self.name,
                    detected_format="pdf_locked",
                    document_kind="unknown",
                    needs_password=True,
                    error="that password did not open this PDF - check it and try again",
                )

            return ExtractionResult(
                extractor=self.name,
                detected_format="pdf_locked",
                document_kind="unknown",
                needs_password=True,
                error="this PDF is password protected - send the password to open it",
            )

        rows: list[ExtractedRow] = []

        characters = 0

        with document:

            for page_number, page in enumerate(document.pages, start=1):

                characters += len(page.extract_text() or "")

                for table in page.extract_tables():

                    index = header_index(table)

                    if index is None:
                        continue

                    headers = cells_as_text(table[index])

                    for offset, line in enumerate(table[index + 1 :], start=index + 2):

                        row = row_to_transaction(cells_as_text(line), headers, page_number, offset)

                        if row is not None:
                            rows.append(row)

        if rows:
            return ExtractionResult(
                extractor=self.name,
                detected_format="pdf_text",
                document_kind="bank_statement",
                rows=rows,
            )

        if characters < MINIMUM_TEXT_CHARACTERS:

            try:
                images = page_images(content, password)

            except Exception as exc:
                return ExtractionResult(
                    extractor=self.name,
                    detected_format="pdf_scan",
                    document_kind="unknown",
                    error=f"this PDF carries no text and could not be rendered: {type(exc).__name__}",
                )

            return await extract_from_images(images, self.name, "pdf_scan")

        return ExtractionResult(
            extractor=self.name,
            detected_format="pdf_text",
            document_kind="unknown",
            error="no transaction table was found in this PDF",
        )
