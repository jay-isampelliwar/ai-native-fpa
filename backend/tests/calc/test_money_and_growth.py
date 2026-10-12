"""Tests for the money helpers and the time-value maths."""

from datetime import date

import pytest

from app.calc.growth import future_value, monthly_sip, months_until_year_end, present_value
from app.calc.money import indian_number, rupees, to_monthly
from app.db.enums import PaymentFrequency


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (999, "999"),
        (1000, "1,000"),
        (100000, "1,00,000"),
        (1000000, "10,00,000"),
        (12345678.4, "1,23,45,678"),
        (-49000, "-49,000"),
        ],
    )
def test_indian_number(value: float, expected: str) -> None:

    """Groups the last three digits, then pairs, as Indian amounts are written."""

    assert indian_number(value) == expected


def test_rupees_rounds_half_up() -> None:

    """Rounds halves up instead of to the nearest even rupee."""

    assert rupees(2.5) == 3

    assert rupees(66666.666) == 66667


def test_to_monthly() -> None:

    """Spreads quarterly, half-yearly and yearly payments over their months."""

    assert to_monthly(3000, PaymentFrequency.quarterly) == 1000

    assert to_monthly(12000, PaymentFrequency.yearly) == 1000

    assert to_monthly(6000, PaymentFrequency.half_yearly) == 1000


def test_months_until_year_end() -> None:

    """Counts to December of the target year, and never below one month."""

    assert months_until_year_end(2027, date(2026, 10, 13)) == 14

    assert months_until_year_end(2026, date(2026, 12, 1)) == 1

    assert months_until_year_end(2020, date(2026, 10, 13)) == 1


def test_future_and_present_value_are_inverse() -> None:

    """Discounting a grown sum gives back the starting sum."""

    grown = future_value(100000, 7, 30)

    assert grown == pytest.approx(100000 * 1.07 ** 2.5)

    assert present_value(grown, 7, 30) == pytest.approx(100000)


def test_monthly_sip() -> None:

    """Matches the annuity formula, splits evenly at zero return, and needs nothing for no target."""

    rate = 0.12 / 12

    assert monthly_sip(1000000, 12, 120) == pytest.approx(1000000 * rate / ((1 + rate) ** 120 - 1))

    assert monthly_sip(120000, 0, 12) == pytest.approx(10000)

    assert monthly_sip(0, 12, 12) == 0
