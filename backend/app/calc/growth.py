"""Time-value maths: months left, growing a sum, discounting a sum, and the monthly SIP that reaches a sum."""

from datetime import date


def months_until_year_end(
    target_year: int,
    today: date,
    ) -> int:

    """Count whole months from today to the end of the target year, at least 1 so a due goal still has a month."""

    months = (target_year - today.year) * 12 + (12 - today.month)

    return max(months, 1)


def future_value(
    amount: float,
    yearly_rate_pct: float,
    months: int,
    ) -> float:

    """Grow a sum at a yearly rate, compounded yearly, over the given months."""

    return amount * (1 + yearly_rate_pct / 100) ** (months / 12)


def present_value(
    amount: float,
    yearly_rate_pct: float,
    months: int,
    ) -> float:

    """Return the sum needed today that grows to the given amount after the given months."""

    return amount / (1 + yearly_rate_pct / 100) ** (months / 12)


def monthly_sip(
    target: float,
    yearly_rate_pct: float,
    months: int,
    ) -> float:

    """Return the equal monthly saving, earning the yearly rate split into months, that grows to the target."""

    if target <= 0:
        return 0.0

    monthly_rate = yearly_rate_pct / 100 / 12

    if monthly_rate == 0:
        return target / months

    return target * monthly_rate / ((1 + monthly_rate) ** months - 1)
