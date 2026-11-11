"""Turning raw cell values into clean numbers, dates, flags and text, failing loudly instead of guessing."""

import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any


EMPTY_TEXT = {"", "-", "--", "na", "n/a", "nil", "none", "null", "not available"}

DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d-%b-%y",
    "%d/%m/%y",
    "%d %B %Y",
    "%Y/%m/%d",
    )

EXCEL_EPOCH = date(1899, 12, 30)

MIN_YEAR = 1900
MAX_YEAR = 2150

CURRENCY_MARKS = re.compile(r"(₹|rs\.?|inr|units?)", re.IGNORECASE)

PLAIN_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")

TRUE_TEXT = {"true", "yes", "y", "1"}
FALSE_TEXT = {"false", "no", "n", "0"}

ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")


class NotReadable(ValueError):

    """A cell value that cannot be turned into the kind of value its field needs."""


def is_empty(raw: Any) -> bool:

    """Whether a cell holds nothing, or a placeholder such as N/A or a dash."""

    if raw is None:
        return True

    if isinstance(raw, str):
        return raw.strip().lower() in EMPTY_TEXT

    return False


def to_decimal(raw: Any) -> Decimal:

    """Read a number from a cell, allowing rupee signs, commas, a units word and brackets for a negative."""

    if isinstance(raw, bool):
        raise NotReadable("is a yes/no value, not a number")

    if isinstance(raw, int):
        return Decimal(raw)

    if isinstance(raw, float):
        return Decimal(repr(raw))

    if isinstance(raw, Decimal):
        return raw

    text = str(raw).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = CURRENCY_MARKS.sub("", text.strip("()")).replace(",", "").replace(" ", "")

    if text.startswith("-"):
        negative = not negative
        text = text[1:]

    if not PLAIN_NUMBER.match(text):
        raise NotReadable("is not a number")

    value = Decimal(text)

    return -value if negative else value


def fixed_places(
    raw: Any,
    places: int
    ) -> Decimal:

    """Read a number and keep it to a fixed number of decimal places, refusing one that would lose digits."""

    value = to_decimal(raw)
    step = Decimal(1).scaleb(-places)

    try:
        rounded = value.quantize(step, rounding=ROUND_HALF_UP)

    except InvalidOperation as exc:
        raise NotReadable("is too large") from exc

    if abs(rounded - value) >= step / 10:
        raise NotReadable(f"has more than {places} decimal places")

    return rounded


def to_money(raw: Any) -> str:

    """A rupee amount to two decimal places, as text so no float ever touches it."""

    return str(fixed_places(raw, 2))


def to_units(raw: Any) -> str:

    """A unit count or price to four decimal places, as text."""

    return str(fixed_places(raw, 4))


def to_rate(raw: Any) -> str:

    """A yearly rate in percent to two decimal places, allowing a percent sign."""

    if isinstance(raw, str):
        raw = raw.replace("%", "")

    return str(fixed_places(raw, 2))


def to_int(raw: Any) -> int:

    """A whole number, refusing one with a fraction."""

    value = to_decimal(raw)

    if value != value.to_integral_value():
        raise NotReadable("is not a whole number")

    return int(value)


def to_year(raw: Any) -> int:

    """A calendar year within sensible bounds."""

    if isinstance(raw, (date, datetime)):
        return raw.year

    year = to_int(raw)

    if not MIN_YEAR <= year <= MAX_YEAR:
        raise NotReadable("is not a sensible year")

    return year


def to_date(raw: Any) -> str:

    """A date as YYYY-MM-DD, reading Excel dates, Excel day numbers and day-first text dates."""

    if isinstance(raw, datetime):
        value = raw.date()

    elif isinstance(raw, date):
        value = raw

    elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = EXCEL_EPOCH + timedelta(days=int(raw))

    else:
        value = parse_date_text(str(raw).strip())

    if not MIN_YEAR <= value.year <= MAX_YEAR:
        raise NotReadable("is not a sensible date")

    return value.isoformat()


def parse_date_text(text: str) -> date:

    """Try each known text date format in turn, day first, and fail when none fits."""

    cleaned = text.split(" 00:00:00")[0].strip()

    for pattern in DATE_FORMATS:

        try:
            return datetime.strptime(cleaned, pattern).date()

        except ValueError:
            continue

    raise NotReadable("is not a date")


def to_bool(raw: Any) -> bool:

    """A yes/no value from a flag cell."""

    if isinstance(raw, bool):
        return raw

    text = str(raw).strip().lower()

    if text in TRUE_TEXT:
        return True

    if text in FALSE_TEXT:
        return False

    raise NotReadable("is not yes or no")


def to_text(raw: Any) -> str:

    """Plain text with spaces tidied, writing whole numbers without a trailing .0 so folio numbers stay intact."""

    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))

    if isinstance(raw, (datetime, date)):
        return raw.isoformat()

    return " ".join(str(raw).split())


def to_isin(raw: Any) -> str:

    """An ISIN in capitals, refusing anything that does not have the twelve character shape."""

    text = to_text(raw).upper().replace(" ", "")

    if not ISIN_PATTERN.match(text):
        raise NotReadable("is not a valid ISIN")

    return text


def header_key(raw: Any) -> str:

    """A header cell in lower case with spaces and punctuation tidied, so small spelling changes still match."""

    text = to_text(raw).lower().replace("’", "'")

    return " ".join(re.sub(r"[^a-z0-9%'()/ ]", " ", text).split())
