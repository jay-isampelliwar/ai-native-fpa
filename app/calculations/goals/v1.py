"""Version 1 of the goal projection, answering whether a target is reachable and what it costs.

Every figure here is arithmetic on typed inputs. No model is involved, and the result carries
the assumptions it used, because a projection quoted without its assumptions is a number
pretending to be a fact.

Two decisions are worth stating plainly. Rates are converted to a monthly figure by dividing
the annual rate by twelve rather than by taking a twelfth root. That is the nominal
convention every Indian SIP calculator uses, so a user checking our number against an AMC's
website sees the same answer - matching the industry convention matters more here than
matching compound interest exactly. Inflation is applied the same way for the same reason,
and both are reported in ``assumptions``.

The target is inflated before anything is compared to it. A house that costs eighty lakh
today does not cost eighty lakh in 2031, and a projection against the sticker price is the
most common way these tools flatter a user into underfunding a goal.

``required_monthly`` is the number people actually act on: what to contribute from now to
close the gap. It is computed against the inflated target and net of what existing assets
will grow into, so it is the additional commitment rather than the total.

A goal already funded past its target returns a zero requirement and says so in a warning,
rather than a negative contribution that a caller might display as a credit.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.calculations.money import ZERO, quantise

CALCULATOR_VERSION = "goals.v1"

MONTHS_PER_YEAR = Decimal("12")


class GoalInput(BaseModel):

    """The typed inputs one goal projection needs, already fetched and permission checked."""

    model_config = {"arbitrary_types_allowed": True}

    target_amount: Decimal
    target_date: date
    as_of: date

    current_corpus: Decimal = Decimal("0")
    monthly_contribution: Decimal = Decimal("0")

    expected_return_percent: Decimal = Decimal("11")
    inflation_percent: Decimal = Decimal("6")


class GoalProjection(BaseModel):

    """What a goal projection concluded, carrying the version and assumptions behind every figure."""

    model_config = {"arbitrary_types_allowed": True}

    calculator_version: str = CALCULATOR_VERSION

    months_remaining: int
    target_today: Decimal
    target_at_maturity: Decimal

    projected_corpus: Decimal
    projected_from_existing: Decimal
    projected_from_contributions: Decimal

    shortfall: Decimal
    required_monthly: Decimal
    on_track: bool

    assumptions: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def months_between(start: date, end: date) -> int:

    """Count whole months from one date to another, never returning a negative horizon."""

    months = (end.year - start.year) * 12 + (end.month - start.month)

    if end.day < start.day:
        months -= 1

    return max(months, 0)


def compound(amount: Decimal, monthly_rate: Decimal, months: int) -> Decimal:

    """Grow one lump sum at a monthly rate for a whole number of months."""

    if months <= 0:
        return amount

    return amount * (Decimal("1") + monthly_rate) ** months


def annuity_future_value(payment: Decimal, monthly_rate: Decimal, months: int) -> Decimal:

    """Grow a level monthly contribution, falling back to a plain sum when the rate is zero."""

    if months <= 0:
        return ZERO

    if monthly_rate == ZERO:
        return payment * months

    return payment * (((Decimal("1") + monthly_rate) ** months - Decimal("1")) / monthly_rate)


def required_payment(gap: Decimal, monthly_rate: Decimal, months: int) -> Decimal:

    """Find the level monthly contribution that closes a gap over the remaining months."""

    if gap <= ZERO or months <= 0:
        return ZERO

    if monthly_rate == ZERO:
        return gap / months

    return gap * monthly_rate / ((Decimal("1") + monthly_rate) ** months - Decimal("1"))


def run_goal_projection(inputs: GoalInput) -> GoalProjection:

    """Project a goal to its target date and report the gap and the contribution that closes it."""

    months = months_between(inputs.as_of, inputs.target_date)

    return_rate = inputs.expected_return_percent / Decimal("100") / MONTHS_PER_YEAR
    inflation_rate = inputs.inflation_percent / Decimal("100") / MONTHS_PER_YEAR

    target_at_maturity = compound(inputs.target_amount, inflation_rate, months)

    from_existing = compound(inputs.current_corpus, return_rate, months)
    from_contributions = annuity_future_value(inputs.monthly_contribution, return_rate, months)

    projected = from_existing + from_contributions
    gap = target_at_maturity - projected

    warnings: list[str] = []

    if months == 0:
        warnings.append("the target date has arrived or passed, so nothing can compound further")

    if gap <= ZERO:
        warnings.append("existing assets and contributions already reach this target")

    if inputs.monthly_contribution == ZERO and inputs.current_corpus == ZERO:
        warnings.append("nothing is currently funding this goal")

    return GoalProjection(
        months_remaining=months,
        target_today=quantise(inputs.target_amount),
        target_at_maturity=quantise(target_at_maturity),
        projected_corpus=quantise(projected),
        projected_from_existing=quantise(from_existing),
        projected_from_contributions=quantise(from_contributions),
        shortfall=quantise(max(gap, ZERO)),
        required_monthly=quantise(required_payment(gap, return_rate, months)),
        on_track=gap <= ZERO,
        assumptions={
            "expected_return_percent": float(inputs.expected_return_percent),
            "inflation_percent": float(inputs.inflation_percent),
            "months_per_year": 12.0,
        },
        warnings=warnings,
    )
