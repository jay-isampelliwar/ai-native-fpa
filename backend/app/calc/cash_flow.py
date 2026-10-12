"""Monthly cash flow maths: what comes in, what goes out, and what is left to save."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.calc.money import rupees, to_monthly
from app.db.enums import PaymentFrequency


@dataclass(frozen=True)
class MonthlyCashFlow:

    """One month's money in and out, each part a whole-rupee monthly amount so the surplus adds up exactly."""

    income: int
    expenses: int
    emis: int
    premiums: int

    @property
    def surplus(self) -> int:

        """Money left each month after expenses, loan EMIs and insurance premiums."""

        return self.income - self.expenses - self.emis - self.premiums


def monthly_total(payments: Iterable[tuple[Decimal | float, PaymentFrequency]]) -> int:

    """Add up payments of any frequency as one monthly amount, rounded to whole rupees."""

    return rupees(sum((to_monthly(amount, frequency) for amount, frequency in payments), 0.0))
