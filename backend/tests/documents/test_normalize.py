"""Tests for turning raw cell values into clean amounts, dates, flags and choices."""

from datetime import datetime

import pytest

from app.features.documents.fields import pick_choice, read_value
from app.features.documents.normalize import NotReadable, is_empty, to_date, to_isin, to_money, to_rate, to_text, to_units


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("₹2,87,500.00", "287500.00"),
        ("-₹5,000", "-5000.00"),
        ("(1,200.50)", "-1200.50"),
        ("Rs. 99", "99.00"),
        (287500, "287500.00"),
        (1234.5, "1234.50"),
        ],
    )
def test_money(
    raw: object,
    expected: str
    ) -> None:

    """Rupee amounts lose signs and commas but keep every rupee."""

    assert to_money(raw) == expected


def test_units_keep_four_places() -> None:

    """Units keep four decimal places and drop the word units."""

    assert to_units("125.4500 Units") == "125.4500"
    assert to_units(1234.567) == "1234.5670"


def test_money_refuses_lost_digits() -> None:

    """An amount with digits beyond the paisa is refused, not rounded away."""

    with pytest.raises(NotReadable):
        to_money("99.999")


def test_money_refuses_text() -> None:

    """Text that is not a number is refused."""

    with pytest.raises(NotReadable):
        to_money("abc")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("31/10/2026", "2026-10-31"),
        ("2026-10-31", "2026-10-31"),
        ("31-Oct-2026", "2026-10-31"),
        (datetime(2026, 10, 31, 0, 0), "2026-10-31"),
        (46326, "2026-10-31"),
        ],
    )
def test_dates_day_first(
    raw: object,
    expected: str
    ) -> None:

    """Dates come out as YYYY-MM-DD, reading text day first and Excel day numbers."""

    assert to_date(raw) == expected


def test_bad_date_refused() -> None:

    """A value that is not a date is refused."""

    with pytest.raises(NotReadable):
        to_date("bad-date")


def test_placeholders_are_empty() -> None:

    """N/A, dashes and blanks count as empty cells."""

    assert is_empty("N/A")
    assert is_empty(" - ")
    assert is_empty(None)
    assert not is_empty(0)


def test_rate_and_text() -> None:

    """Rates drop the percent sign; whole floats keep folio numbers intact."""

    assert to_rate("8.5%") == "8.50"
    assert to_text(12345678.0) == "12345678"


def test_isin_shape() -> None:

    """ISINs come out in capitals, and a wrong shape is refused."""

    assert to_isin("ine002a01018") == "INE002A01018"

    with pytest.raises(NotReadable):
        to_isin("INE002")


@pytest.mark.parametrize(
    ("kind", "raw", "expected"),
    [
        ("expense_category", "Rent / Maintenance", "rent"),
        ("expense_category", "Parents support", "family_support"),
        ("expense_category", "Household help", "household_help"),
        ("expense_category", "Children — Fees & Activities", "education"),
        ("income_source_type", "Rental Income", "rent"),
        ("risk_appetite", "Aggressive", "high"),
        ("physical_asset_type", "Residential — self-occupied", "real_estate"),
        ("retirement_account_type", "PPF", "ppf"),
        ("deposit_type", "FD", "fd"),
        ("loan_type", "Education Loan", "education"),
        ],
    )
def test_choices(
    kind: str,
    raw: str,
    expected: str
    ) -> None:

    """Words in a cell pick the right choice, and a word inside another word does not."""

    assert pick_choice(kind, raw) == expected


def test_unknown_choice_refused() -> None:

    """Text that names no known choice is refused, not guessed."""

    with pytest.raises(NotReadable):
        pick_choice("retirement_account_type", "FD")


def test_priority_words_and_numbers() -> None:

    """Importance words and plain numbers both become a priority number."""

    assert read_value("priority", "Essential") == 1
    assert read_value("priority", 2) == 2
