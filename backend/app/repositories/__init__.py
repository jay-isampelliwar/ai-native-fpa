"""One place that decides which repository implementation the application runs against.

Skills depend on the protocols, never on a concrete class, so the choice between the seeded
dictionaries and PostgreSQL is made here and nowhere else. That keeps the switch to a single
setting rather than an import that has to be found and changed in every skill.

The in-memory implementations are kept rather than deleted. They make the test suite fast
and offline, and more usefully they are the fixture the same repository tests run against,
so a behavioural difference between the two backends shows up as a failing test rather than
as a surprise in production.

``sql`` is the default because it is what the application actually runs. A test that wants
the seeded data asks for it explicitly, which means a test that forgets to is exercising the
real code path rather than silently passing against a dictionary.
"""

from functools import lru_cache

from app.core.config import settings
from app.repositories.cashflow_repository import CashflowRepository, InMemoryCashflowRepository
from app.repositories.expense_repository import ExpenseRepository, InMemoryExpenseRepository
from app.repositories.sql_cashflow_repository import SqlCashflowRepository
from app.repositories.sql_expense_repository import SqlExpenseRepository


@lru_cache
def get_cashflow_repository() -> CashflowRepository:

    """Return the configured cash flow repository, SQL unless the settings ask for memory."""

    if settings.repository_backend == "memory":
        return InMemoryCashflowRepository()

    return SqlCashflowRepository()


@lru_cache
def get_expense_repository() -> ExpenseRepository:

    """Return the configured expense repository, SQL unless the settings ask for memory."""

    if settings.repository_backend == "memory":
        return InMemoryExpenseRepository()

    return SqlExpenseRepository()
