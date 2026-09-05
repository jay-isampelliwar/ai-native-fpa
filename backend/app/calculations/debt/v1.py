"""Version 1 of the debt calculators: what an EMI is, and which repayment order clears debt sooner.

The EMI formula here is the standard reducing balance one every Indian lender uses, so a
figure this module produces should match a loan statement to the rupee. Where it does not,
the difference is in the lender's day count or rounding rather than in the method, and that
is worth knowing rather than hiding behind an approximation.

The strategy comparison is a month by month simulation rather than a closed form. Closed
forms exist for a single loan, but the question people actually ask involves several loans, a
fixed extra payment, and an ordering rule - and once a loan is cleared its EMI rolls into the
next one, which no formula captures cleanly. Simulating is slower and correct.

Avalanche pays the highest rate first and is arithmetically optimal. Snowball pays the
smallest balance first and clears individual loans sooner. Both are computed and returned
because the better one depends on whether the user needs the money or the momentum, and that
is not a judgement a calculator should make silently.

The simulation has a hard iteration ceiling. A payment too small to cover accruing interest
would otherwise loop until the process is killed, so that case terminates and is reported as
a warning saying the debt never clears - which is the finding.
"""

from decimal import Decimal

from pydantic import BaseModel, Field

from app.calculations.money import ZERO, quantise

CALCULATOR_VERSION = "debt.v1"

MONTHS_PER_YEAR = Decimal("12")
MAXIMUM_MONTHS = 600


class LoanInput(BaseModel):

    """One outstanding debt, described the way a loan statement describes it."""

    model_config = {"arbitrary_types_allowed": True}

    id: str
    label: str
    principal_outstanding: Decimal
    annual_rate_percent: Decimal
    minimum_payment: Decimal


class StrategyResult(BaseModel):

    """How one repayment ordering performed, in the two terms a borrower cares about."""

    model_config = {"arbitrary_types_allowed": True}

    strategy: str
    months_to_clear: int
    total_interest: Decimal
    payoff_order: list[str] = Field(default_factory=list)
    cleared: bool = True


class DebtComparison(BaseModel):

    """Both repayment strategies side by side, with the difference between them made explicit."""

    model_config = {"arbitrary_types_allowed": True}

    calculator_version: str = CALCULATOR_VERSION

    avalanche: StrategyResult
    snowball: StrategyResult

    interest_saved_by_avalanche: Decimal
    months_saved_by_avalanche: int

    assumptions: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def monthly_emi(principal: Decimal, annual_rate_percent: Decimal, months: int) -> Decimal:

    """Compute the level payment that clears a reducing balance loan over its tenure."""

    if months <= 0:
        return ZERO

    rate = annual_rate_percent / Decimal("100") / MONTHS_PER_YEAR

    if rate == ZERO:
        return quantise(principal / months)

    growth = (Decimal("1") + rate) ** months

    return quantise(principal * rate * growth / (growth - Decimal("1")))


def total_interest(principal: Decimal, annual_rate_percent: Decimal, months: int) -> Decimal:

    """Report how much of a loan's repayment is interest rather than principal."""

    return quantise(monthly_emi(principal, annual_rate_percent, months) * months - principal)


def simulate(loans: list[LoanInput], extra_monthly: Decimal, order_key) -> StrategyResult:

    """Run one repayment ordering month by month, rolling cleared payments into the next target."""

    balances = {loan.id: loan.principal_outstanding for loan in loans}
    rates = {loan.id: loan.annual_rate_percent / Decimal("100") / MONTHS_PER_YEAR for loan in loans}
    minimums = {loan.id: loan.minimum_payment for loan in loans}

    interest_paid = ZERO
    payoff_order: list[str] = []
    month = 0

    while any(balance > ZERO for balance in balances.values()) and month < MAXIMUM_MONTHS:

        month += 1

        for loan_id, balance in balances.items():

            if balance > ZERO:
                accrued = balance * rates[loan_id]
                interest_paid += accrued
                balances[loan_id] = balance + accrued

        budget = extra_monthly + sum(
            (minimums[loan_id] for loan_id, balance in balances.items() if balance > ZERO),
            ZERO,
        )

        outstanding = [loan for loan in loans if balances[loan.id] > ZERO]

        for loan in sorted(outstanding, key=lambda item: order_key(item, balances)):

            if budget <= ZERO:
                break

            payment = min(budget, balances[loan.id])

            balances[loan.id] -= payment
            budget -= payment

            if balances[loan.id] <= ZERO and loan.id not in payoff_order:
                payoff_order.append(loan.id)

    cleared = all(balance <= ZERO for balance in balances.values())

    return StrategyResult(
        strategy="",
        months_to_clear=month,
        total_interest=quantise(interest_paid),
        payoff_order=payoff_order,
        cleared=cleared,
    )


def compare_strategies(loans: list[LoanInput], extra_monthly: Decimal = ZERO) -> DebtComparison:

    """Compare paying highest rate first against smallest balance first, reporting both outcomes."""

    avalanche = simulate(loans, extra_monthly, lambda loan, balances: -loan.annual_rate_percent)
    avalanche.strategy = "avalanche"

    snowball = simulate(loans, extra_monthly, lambda loan, balances: balances[loan.id])
    snowball.strategy = "snowball"

    warnings: list[str] = []

    if not avalanche.cleared or not snowball.cleared:
        warnings.append("payments do not cover the interest accruing, so this debt does not clear")

    if avalanche.months_to_clear == snowball.months_to_clear and avalanche.total_interest == snowball.total_interest:
        warnings.append("both strategies are identical here, which happens with a single loan")

    return DebtComparison(
        avalanche=avalanche,
        snowball=snowball,
        interest_saved_by_avalanche=quantise(snowball.total_interest - avalanche.total_interest),
        months_saved_by_avalanche=snowball.months_to_clear - avalanche.months_to_clear,
        assumptions={"extra_monthly": float(extra_monthly), "months_per_year": 12.0},
        warnings=warnings,
    )
