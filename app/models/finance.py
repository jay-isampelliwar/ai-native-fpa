"""The financial records the planner reads, one type per real world thing.

These are the shapes the application database owns and the agent never invents. Each
record carries a stable ``id`` because that id is what a skill returns as evidence: a
conclusion the user can trace back to the exact rows it came from, rather than a number
the model asserts.

The types stay separate even where the fields look similar, because the doc's modelling
distinction matters downstream. An expense is money leaving with nothing owed after it,
an EMI is a contractual obligation attached to a liability, and an SIP is a standing
instruction pointed at a mutual fund scheme. Collapsing them into one "outflow" table
would make it impossible for the cash flow calculator to separate committed from
discretionary spending, which is the distinction most advice turns on.

``amount`` is stored at its natural frequency, not pre-divided, because that is how the
user knows it - a salary is monthly, an insurance premium is annual. ``monthly_amount``
converts on read. That conversion is a unit change rather than financial modelling, which
is why it lives here instead of in a versioned calculator, and it is the only arithmetic
any model in this package performs.

Nothing here has a ``user_id`` accessor used for filtering by callers. Ownership is
enforced in the repository layer, so a skill holding a record can never widen its own
access by asking for a different user.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from app.calculations.money import quantise


class Frequency(StrEnum):

    """How often a recorded amount actually occurs, before it is normalised to a month."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    ANNUAL = "annual"


MONTHS_PER = {
    Frequency.MONTHLY: Decimal("1"),
    Frequency.QUARTERLY: Decimal("3"),
    Frequency.HALF_YEARLY: Decimal("6"),
    Frequency.ANNUAL: Decimal("12"),
}


class FinancialRecord(BaseModel):

    """Fields every planner record shares, including the id a skill quotes back as evidence."""

    model_config = {"arbitrary_types_allowed": True}

    id: str
    user_id: int
    label: str
    amount: Decimal
    frequency: Frequency = Frequency.MONTHLY
    active: bool = True

    @property
    def monthly_amount(self) -> Decimal:

        """Normalise the recorded amount to one month, which is the unit every calculator expects."""

        return quantise(self.amount / MONTHS_PER[self.frequency])


class IncomeRecord(FinancialRecord):

    """Money arriving on a schedule, such as salary, rent, interest or a dividend."""

    source: str = "salary"


class ExpenseRecord(FinancialRecord):

    """Money leaving with no obligation attached once it is paid, such as groceries or a subscription."""

    category: str = "general"


class EmiRecord(FinancialRecord):

    """A contractual repayment against a liability, which cannot be paused the way an SIP can."""

    liability_id: str
    interest_rate_percent: Decimal
    remaining_months: int


class SipRecord(FinancialRecord):

    """A standing instruction into a mutual fund scheme, discretionary and therefore adjustable."""

    scheme_name: str
    folio_id: str | None = None
    next_debit_on: date | None = None
    linked_goal_id: str | None = None


class CashflowRecords(BaseModel):

    """Everything one cash flow question needs, fetched together so a single evidence set covers the answer."""

    income: list[IncomeRecord] = Field(default_factory=list)
    expenses: list[ExpenseRecord] = Field(default_factory=list)
    emis: list[EmiRecord] = Field(default_factory=list)
    sips: list[SipRecord] = Field(default_factory=list)

    @property
    def evidence_ids(self) -> list[str]:

        """List every record id behind this answer, so the user can trace the conclusion to its rows."""

        return [
            record.id
            for group in (self.income, self.expenses, self.emis, self.sips)
            for record in group
        ]
