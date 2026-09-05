"""Version 1 of the monthly cash flow calculator, the deterministic core of most skills.

Nothing in this module talks to a model, a database or the network. It takes typed
amounts and returns typed amounts, which is what makes it testable against known answers
and what makes its output safe to quote to a user as fact. Every skill that needs a
surplus figure calls this rather than computing its own, so two skills cannot disagree
about the same month.

The version lives in the module path and in ``CALCULATOR_VERSION``, and that string is
written into every result and every audit record. When the formula changes we add
``v2.py`` beside this file rather than editing it, because a plan a user approved six
months ago must still be explainable using the arithmetic that produced it.

The distinction the calculator enforces is between committed and discretionary outflow.
EMIs are contractual and cannot be skipped; SIPs are voluntary and can be paused. Free
surplus subtracts both, but ``investable_surplus`` adds SIPs back, because the question
"can I raise my SIP by five thousand" is asking how much room exists once the SIP that
is already running is set aside.

Assumptions and warnings travel with the result rather than being logged and forgotten.
A negative surplus or a savings rate near zero is not an error - it is the finding - so
it is returned as a warning the explaining skill must show the user.
"""

from decimal import Decimal

from pydantic import BaseModel, Field

from app.calculations.money import ZERO, percentage, quantise, total

CALCULATOR_VERSION = "cashflow.v1"


class CashflowInput(BaseModel):

    """The typed monthly amounts one cash flow run needs, already fetched and permission checked."""

    model_config = {"arbitrary_types_allowed": True}

    income: list[Decimal] = Field(default_factory=list)
    expenses: list[Decimal] = Field(default_factory=list)
    emis: list[Decimal] = Field(default_factory=list)
    sips: list[Decimal] = Field(default_factory=list)


class CashflowResult(BaseModel):

    """One month's verified cash flow figures, carrying the calculator version and any warnings."""

    model_config = {"arbitrary_types_allowed": True}

    calculator_version: str = CALCULATOR_VERSION

    total_income: Decimal
    total_expenses: Decimal
    total_emis: Decimal
    total_sips: Decimal

    committed_outflow: Decimal
    free_surplus: Decimal
    investable_surplus: Decimal
    savings_rate_percent: Decimal

    warnings: list[str] = Field(default_factory=list)


def run_cashflow(inputs: CashflowInput) -> CashflowResult:

    """Compute one month's surplus and savings rate from typed amounts, returning findings as warnings."""

    total_income = total(inputs.income)
    total_expenses = total(inputs.expenses)
    total_emis = total(inputs.emis)
    total_sips = total(inputs.sips)

    committed_outflow = quantise(total_expenses + total_emis)
    free_surplus = quantise(total_income - committed_outflow - total_sips)
    investable_surplus = quantise(free_surplus + total_sips)

    warnings: list[str] = []

    if total_income == ZERO:
        warnings.append("no income was recorded for this period, so every ratio is unreliable")

    if free_surplus < ZERO:
        warnings.append("committed outflow exceeds income, so this month runs at a deficit")

    if total_emis > quantise(total_income / 2) and total_income > ZERO:
        warnings.append("EMIs consume more than half of income, which leaves little room to absorb a shock")

    return CashflowResult(
        total_income=total_income,
        total_expenses=total_expenses,
        total_emis=total_emis,
        total_sips=total_sips,
        committed_outflow=committed_outflow,
        free_surplus=free_surplus,
        investable_surplus=investable_surplus,
        savings_rate_percent=percentage(free_surplus, total_income),
        warnings=warnings,
    )
