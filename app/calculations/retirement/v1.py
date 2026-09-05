"""Version 1 of the retirement projection, covering both accumulation and withdrawal.

Retirement is two problems joined at one date and this module keeps them visibly separate.
Accumulation asks what the corpus will be worth at retirement; withdrawal asks what corpus
is needed to fund spending after it. Tools that model only the first produce a number with
nothing to compare it against, which is how someone ends up confident about a corpus that
funds eleven years of a thirty year retirement.

The withdrawal side uses a real rate of return rather than a fixed withdrawal percentage.
Expenses rise with inflation for the whole of retirement, so the corpus has to outpace
inflation, not just returns - the real rate is the honest way to say that, and it collapses
correctly when returns and inflation are equal.

Post retirement returns default lower than pre retirement returns because the portfolio is
expected to shift towards income. That default is an assumption and it is reported as one;
it is the single input most worth overriding for a real user.

Every rate is converted to a monthly figure by dividing by twelve, matching the convention
in the goal calculator so that two projections about the same person cannot disagree about
what an eleven percent return means.

``longevity_years`` is how long the corpus must last, not a life expectancy. It defaults to
thirty because planning to the average means half of people outlive their money.

The affordability warning is checked against the required contribution, never against the
shortfall divided by the remaining months. Those two differ by everything compounding does -
over twenty eight years the naive figure is several times the real one - and warning on it
would tell a user their plan is unrealistic when it is comfortably fundable.
"""

from decimal import Decimal

from pydantic import BaseModel, Field

from app.calculations.money import ZERO, quantise

CALCULATOR_VERSION = "retirement.v1"

MONTHS_PER_YEAR = Decimal("12")


class RetirementInput(BaseModel):

    """The typed inputs one retirement projection needs, with every rate stated annually."""

    model_config = {"arbitrary_types_allowed": True}

    current_age: int
    retirement_age: int
    longevity_years: int = 30

    current_corpus: Decimal = Decimal("0")
    monthly_contribution: Decimal = Decimal("0")
    current_monthly_expense: Decimal

    pre_retirement_return_percent: Decimal = Decimal("11")
    post_retirement_return_percent: Decimal = Decimal("7")
    inflation_percent: Decimal = Decimal("6")


class RetirementProjection(BaseModel):

    """What a retirement projection concluded, split into what will be there and what is needed."""

    model_config = {"arbitrary_types_allowed": True}

    calculator_version: str = CALCULATOR_VERSION

    years_to_retirement: int
    months_to_retirement: int

    monthly_expense_at_retirement: Decimal
    corpus_required: Decimal
    corpus_projected: Decimal

    shortfall: Decimal
    required_additional_monthly: Decimal
    on_track: bool

    assumptions: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def compound(amount: Decimal, monthly_rate: Decimal, months: int) -> Decimal:

    """Grow one lump sum at a monthly rate for a whole number of months."""

    if months <= 0:
        return amount

    return amount * (Decimal("1") + monthly_rate) ** months


def annuity_future_value(payment: Decimal, monthly_rate: Decimal, months: int) -> Decimal:

    """Grow a level monthly contribution to the end of the accumulation period."""

    if months <= 0:
        return ZERO

    if monthly_rate == ZERO:
        return payment * months

    return payment * (((Decimal("1") + monthly_rate) ** months - Decimal("1")) / monthly_rate)


def corpus_for_withdrawals(monthly_expense: Decimal, real_monthly_rate: Decimal, months: int) -> Decimal:

    """Find the corpus that funds an inflation adjusted monthly expense for a fixed number of months."""

    if months <= 0:
        return ZERO

    if real_monthly_rate <= ZERO:
        return monthly_expense * months

    factor = Decimal("1") - (Decimal("1") + real_monthly_rate) ** (-months)

    return monthly_expense * factor / real_monthly_rate


def required_payment(gap: Decimal, monthly_rate: Decimal, months: int) -> Decimal:

    """Find the extra monthly contribution that closes a shortfall by the retirement date."""

    if gap <= ZERO or months <= 0:
        return ZERO

    if monthly_rate == ZERO:
        return gap / months

    return gap * monthly_rate / ((Decimal("1") + monthly_rate) ** months - Decimal("1"))


def run_retirement_projection(inputs: RetirementInput) -> RetirementProjection:

    """Project the corpus at retirement against the corpus retirement needs, and report the gap."""

    years = max(inputs.retirement_age - inputs.current_age, 0)
    months = years * 12

    pre_rate = inputs.pre_retirement_return_percent / Decimal("100") / MONTHS_PER_YEAR
    post_rate = inputs.post_retirement_return_percent / Decimal("100") / MONTHS_PER_YEAR
    inflation_rate = inputs.inflation_percent / Decimal("100") / MONTHS_PER_YEAR

    real_rate = (Decimal("1") + post_rate) / (Decimal("1") + inflation_rate) - Decimal("1")

    expense_at_retirement = compound(inputs.current_monthly_expense, inflation_rate, months)

    corpus_required = corpus_for_withdrawals(
        expense_at_retirement,
        real_rate,
        inputs.longevity_years * 12,
    )

    corpus_projected = compound(inputs.current_corpus, pre_rate, months) + annuity_future_value(
        inputs.monthly_contribution,
        pre_rate,
        months,
    )

    gap = corpus_required - corpus_projected

    additional_monthly = required_payment(gap, pre_rate, months)

    warnings: list[str] = []

    if years == 0:
        warnings.append("retirement age has been reached, so nothing accumulates further")

    if inputs.post_retirement_return_percent <= inputs.inflation_percent:
        warnings.append("post retirement returns do not beat inflation, so the corpus is drawn down in real terms")

    if additional_monthly > inputs.current_monthly_expense:
        warnings.append("closing this shortfall would cost more each month than current expenses, so the target may be unrealistic")

    return RetirementProjection(
        years_to_retirement=years,
        months_to_retirement=months,
        monthly_expense_at_retirement=quantise(expense_at_retirement),
        corpus_required=quantise(corpus_required),
        corpus_projected=quantise(corpus_projected),
        shortfall=quantise(max(gap, ZERO)),
        required_additional_monthly=quantise(additional_monthly),
        on_track=gap <= ZERO,
        assumptions={
            "pre_retirement_return_percent": float(inputs.pre_retirement_return_percent),
            "post_retirement_return_percent": float(inputs.post_retirement_return_percent),
            "inflation_percent": float(inputs.inflation_percent),
            "longevity_years": float(inputs.longevity_years),
        },
        warnings=warnings,
    )
