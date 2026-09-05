"""Coercing spreadsheet cells into the types the database expects, and refusing what cannot be read.

Statements store numbers as text more often than not. A rupee amount arrives as ``₹1,02,031.65``, a
return as ``24.27%``, a quantity as ``1215.0349999999999``, and a date in whichever of six formats
the exporting system preferred. Every one of those has to become a typed value before it can be
stored, and every one of them has a plausible wrong reading.

Percentages are the worst offender because they arrive both ways. ``24.27%`` is text meaning
twenty four percent; ``0.3054`` is a float meaning thirty percent. Reading the second as thirty
percent *points* would be wrong by two orders of magnitude, so the rule here is explicit: a string
with a percent sign is divided by a hundred, a bare number below one is already a fraction, and a
bare number above one is treated as percent and converted. Each case is stated rather than inferred
from context.

Money goes through ``to_money`` and therefore never touches a float. A spreadsheet is the one place
where numbers arrive as text and could silently lose precision on the way in, which is exactly what
``app.calculations.money`` exists to prevent.

Nothing here guesses at a value it cannot read. A cell that will not parse returns ``None`` and the
caller lowers the row's confidence, because a zero substituted for an unreadable amount is a number
that looks correct in a total and is not.

Indian digit grouping is handled by stripping separators rather than by locale parsing. ``1,02,031``
groups differently from ``102,031`` and no standard parser reads both, but with commas removed they
are the same digits.
"""

from datetime import date, datetime
from decimal import Decimal

from app.calculations.money import MoneyError, to_money

CURRENCY_MARKERS = ("₹", "rs.", "rs", "inr")

DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%B %d, %Y",
    "%d-%b-%y",
)


def clean_text(value: object) -> str:

    """Reduce a cell to trimmed text, treating the several spellings of empty as the same thing."""

    if value is None:
        return ""

    text = str(value).strip()

    if text.lower() in {"", "-", "--", "n/a", "na", "nil", "none"}:
        return ""

    return text


def strip_numeric(text: str) -> str:

    """Remove currency markers, separators and stray symbols, leaving digits, sign and point."""

    lowered = text.lower()

    for marker in CURRENCY_MARKERS:
        lowered = lowered.replace(marker, "")

    return lowered.replace(",", "").replace("%", "").replace("(", "-").replace(")", "").strip()


def to_decimal(value: object) -> Decimal | None:

    """Read any cell as a number, returning None rather than substituting a misleading zero."""

    text = clean_text(value)

    if not text:
        return None

    try:
        return to_money(strip_numeric(text))

    except MoneyError:
        return None


def to_money_value(value: object) -> Decimal | None:

    """Read a currency cell, tolerating rupee symbols and Indian digit grouping."""

    return to_decimal(value)


def to_quantity(value: object) -> Decimal | None:

    """Read a unit count, which for mutual funds carries three or more decimal places."""

    return to_decimal(value)


def to_fraction(value: object) -> Decimal | None:

    """Read a return as a fraction, distinguishing a percent string from a value already fractional."""

    text = clean_text(value)

    if not text:
        return None

    has_percent_sign = "%" in text

    number = to_decimal(text)

    if number is None:
        return None

    if has_percent_sign:
        return number / Decimal("100")

    if abs(number) <= Decimal("1"):
        return number

    return number / Decimal("100")


def to_date(value: object) -> date | None:

    """Read a date cell against known formats, accepting one a spreadsheet already typed for us."""

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = clean_text(value)

    if not text:
        return None

    for pattern in DATE_FORMATS:

        try:
            return datetime.strptime(text, pattern).date()

        except ValueError:
            continue

    return None


def looks_like_total_row(cells: list[object]) -> bool:

    """Recognise a statement's own total line, which must never be imported as a holding."""

    first = clean_text(cells[0] if cells else "").lower()

    return first.startswith(("total", "grand total", "sum", "net total")) or first in {"totals"}
