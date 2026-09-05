"""Deterministic extraction of bank transactions from a CSV statement.

This extractor exists to be boring. A CSV with recognisable headers has exactly one correct
reading, so nothing here infers, guesses or asks a model - it maps columns and reports 1.0
confidence. Every format that can be handled this way should be, because a deterministic parser
that is wrong is wrong reproducibly and can be fixed, while an inferred reading that is wrong is
wrong differently each time.

Header matching is by alias rather than by position. Indian banks export the same six columns
under a dozen different names, and matching "Withdrawal Amt.", "Debit" and "Dr" to the same field
is the difference between supporting three banks and supporting most of them.

Debits and credits arrive in separate columns far more often than as one signed amount, and a row
with a value in the credit column is money arriving, not a negative expense. Rows that are credits
are skipped rather than stored as negative spending, because an income row masquerading as a
refund distorts every category total afterwards.

Dates are tried against a list of formats rather than parsed loosely. ``03/04/2026`` is the fourth
of March in one convention and the third of April in another, and guessing produces transactions
in the wrong month with nothing to show anything went wrong. Indian statements are day first, so
that is tried first and an unparseable date lowers confidence rather than failing the row.

Amounts go through ``to_money`` and therefore never touch a float. A statement is the one place
where the numbers arrive as text and could quietly become imprecise on the way in.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal

from app.calculations.money import MoneyError, to_money
from app.extraction.base import ExtractedRow, ExtractionResult

DATE_ALIASES = ("date", "txn date", "transaction date", "value date", "posting date", "tran date")
DESCRIPTION_ALIASES = ("description", "narration", "particulars", "transaction remarks", "details", "remarks")
DEBIT_ALIASES = ("debit", "withdrawal", "withdrawal amt.", "withdrawal amount", "dr", "debit amount", "amount debited")
CREDIT_ALIASES = ("credit", "deposit", "deposit amt.", "deposit amount", "cr", "credit amount", "amount credited")
AMOUNT_ALIASES = ("amount", "txn amount", "transaction amount")

DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%d", "%m/%d/%Y")

CATEGORY_HINTS = {
    "rent": ("rent", "landlord"),
    "groceries": ("bigbasket", "dmart", "grocer", "supermarket", "blinkit", "zepto"),
    "dining": ("swiggy", "zomato", "restaurant", "cafe", "eatery"),
    "transport": ("uber", "ola", "rapido", "irctc", "petrol", "fuel"),
    "subscriptions": ("netflix", "spotify", "prime", "subscription", "hotstar"),
    "shopping": ("amazon", "flipkart", "myntra", "croma", "reliance digital"),
    "utilities": ("electricity", "broadband", "airtel", "jio", "gas", "water"),
}


def normalise(header: str) -> str:

    """Reduce a column heading to a comparable form, since banks differ on case and padding."""

    return header.strip().lower().replace("_", " ")


def find_column(headers: list[str], aliases: tuple[str, ...]) -> str | None:

    """Find which of a statement's columns holds a field, matching known names rather than a position."""

    lookup = {normalise(header): header for header in headers}

    for alias in aliases:

        if alias in lookup:
            return lookup[alias]

    for normalised, original in lookup.items():

        if any(alias in normalised for alias in aliases):
            return original

    return None


def parse_date(value: str) -> tuple[str | None, str | None]:

    """Parse a statement date against known formats, day first, reporting when none matched."""

    cleaned = value.strip()

    for pattern in DATE_FORMATS:

        try:
            return datetime.strptime(cleaned, pattern).date().isoformat(), None

        except ValueError:
            continue

    return None, f"could not read the date {cleaned!r}"


def parse_amount(value: str) -> Decimal | None:

    """Read an amount from a statement cell, ignoring separators and treating blanks as absent."""

    cleaned = value.strip().replace(",", "").replace("₹", "").replace("INR", "").strip()

    if not cleaned or cleaned in {"-", "0", "0.00"}:
        return None

    try:
        return to_money(cleaned)

    except MoneyError:
        return None


def guess_category(description: str) -> str:

    """Suggest a category from the narration, which a person can correct on the reconcile screen."""

    lowered = description.lower()

    for category, hints in CATEGORY_HINTS.items():

        if any(hint in lowered for hint in hints):
            return category

    return "uncategorised"


class BankCsvExtractor:

    """Reads bank transactions from a CSV statement by mapping known column names."""

    name = "bank_csv.v1"

    def can_handle(self, filename: str, content_type: str, head: bytes) -> bool:

        """Claim a document only when it is CSV text whose header names a date and a description."""

        if not filename.lower().endswith(".csv") and "csv" not in content_type:
            return False

        try:
            first_line = head.decode("utf-8", errors="ignore").splitlines()[0]

        except IndexError:
            return False

        headers = [normalise(column) for column in first_line.split(",")]

        return find_column(headers, DATE_ALIASES) is not None

    async def extract(self, content: bytes, filename: str) -> ExtractionResult:

        """Map every debit row to a transaction, skipping credits and flagging what could not be read."""

        text = content.decode("utf-8-sig", errors="replace")

        reader = csv.DictReader(io.StringIO(text))

        headers = reader.fieldnames or []

        date_column = find_column(headers, DATE_ALIASES)
        description_column = find_column(headers, DESCRIPTION_ALIASES)
        debit_column = find_column(headers, DEBIT_ALIASES)
        credit_column = find_column(headers, CREDIT_ALIASES)
        amount_column = find_column(headers, AMOUNT_ALIASES)

        if date_column is None or (debit_column is None and amount_column is None):
            return ExtractionResult(
                extractor=self.name,
                detected_format="bank_csv",
                document_kind="bank_statement",
                error="this CSV does not have a recognisable date and amount column",
            )

        rows: list[ExtractedRow] = []

        for index, record in enumerate(reader):

            row = self._row_from(record, index, date_column, description_column, debit_column, credit_column, amount_column)

            if row is not None:
                rows.append(row)

        return ExtractionResult(
            extractor=self.name,
            detected_format="bank_csv",
            document_kind="bank_statement",
            rows=rows,
        )

    def _row_from(
        self,
        record: dict,
        index: int,
        date_column: str,
        description_column: str | None,
        debit_column: str | None,
        credit_column: str | None,
        amount_column: str | None,
        ) -> ExtractedRow | None:

        """Turn one statement line into a staged transaction, or skip it when it is not a spend."""

        if credit_column and parse_amount(record.get(credit_column, "") or "") is not None:
            return None

        amount = None

        if debit_column:
            amount = parse_amount(record.get(debit_column, "") or "")

        if amount is None and amount_column:
            amount = parse_amount(record.get(amount_column, "") or "")

        if amount is None:
            return None

        occurred_on, date_issue = parse_date(record.get(date_column, "") or "")

        description = (record.get(description_column, "") or "").strip() if description_column else ""

        confidence = Decimal("1.000")

        if date_issue:
            confidence = Decimal("0.400")

        elif not description:
            confidence = Decimal("0.800")

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
        )
