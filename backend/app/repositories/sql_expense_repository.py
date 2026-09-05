"""The SQL implementation of the transaction reads a spending investigation performs.

The category totals are computed by the database rather than in Python. An investigation
starts by asking what a month looked like, and pulling every transaction back just to sum
them would move a year of spending through the application for a result that is a dozen
numbers - and, in an agent loop, into a model's context.

``MAXIMUM_ROWS`` is applied as a ``LIMIT`` in the query, not as a slice afterwards. The
in-memory implementation could get away with the latter; against a real table it is the
difference between reading fifty rows and reading all of them.

Every method takes ``user_id`` from the caller's authenticated context and puts it in the
``WHERE`` clause. The agent's tools close over that value, so there is no path by which a
model can influence which user's transactions a query returns.

Amounts come back as ``Decimal`` because the column is ``NUMERIC``. They are turned into
strings at the tool boundary, not here - the repository's job is to return the value with
its precision intact and let the layer facing the model decide how to present it.
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_scope
from app.models.finance import ExpenseTransaction
from app.models.orm.cashflow import ExpenseTransactionRow

MAXIMUM_ROWS = 50


class SqlExpenseRepository:

    """Reads one user's dated transactions and monthly category totals from PostgreSQL."""

    def __init__(self, session: AsyncSession | None = None) -> None:

        """Take a session to reuse, or open one per call when running outside a unit of work."""

        self._session = session

    async def list_transactions(
        self,
        user_id: int,
        year: int | None = None,
        month: int | None = None,
        category: str | None = None,
        limit: int = MAXIMUM_ROWS,
        ) -> list[ExpenseTransaction]:

        """Return this user's transactions for an optional month and category, newest first and capped."""

        statement = select(ExpenseTransactionRow).where(ExpenseTransactionRow.user_id == user_id)

        if year is not None:
            statement = statement.where(func.extract("year", ExpenseTransactionRow.occurred_on) == year)

        if month is not None:
            statement = statement.where(func.extract("month", ExpenseTransactionRow.occurred_on) == month)

        if category is not None:
            statement = statement.where(ExpenseTransactionRow.category == category.lower())

        statement = statement.order_by(ExpenseTransactionRow.occurred_on.desc()).limit(min(limit, MAXIMUM_ROWS))

        async with self._scope() as session:
            rows = await session.scalars(statement)

            return [
                ExpenseTransaction(
                    id=row.id,
                    user_id=row.user_id,
                    occurred_on=row.occurred_on,
                    amount=row.amount,
                    category=row.category,
                    merchant=row.merchant,
                    description=row.description,
                )
                for row in rows
            ]

    async def category_totals(
        self,
        user_id: int,
        year: int,
        month: int,
        ) -> dict[str, Decimal]:

        """Total this user's spending per category for one month, aggregated by the database."""

        statement = (
            select(
                ExpenseTransactionRow.category,
                func.sum(ExpenseTransactionRow.amount).label("total"),
            )
            .where(
                ExpenseTransactionRow.user_id == user_id,
                func.extract("year", ExpenseTransactionRow.occurred_on) == year,
                func.extract("month", ExpenseTransactionRow.occurred_on) == month,
            )
            .group_by(ExpenseTransactionRow.category)
            .order_by(func.sum(ExpenseTransactionRow.amount).desc())
        )

        async with self._scope() as session:
            rows = (await session.execute(statement)).all()

            return {category: total for category, total in rows}

    def _scope(self):

        """Reuse the injected session when there is one, otherwise open a short lived unit of work."""

        if self._session is not None:
            return _ExistingSession(self._session)

        return session_scope()


class _ExistingSession:

    """Adapts an already open session to the context manager shape the query methods use."""

    def __init__(self, session: AsyncSession) -> None:

        """Hold the session that the caller owns and will close itself."""

        self._session = session

    async def __aenter__(self) -> AsyncSession:

        """Hand back the existing session without opening anything."""

        return self._session

    async def __aexit__(self, *exc_info) -> bool:

        """Leave the session open, since its lifetime belongs to whoever injected it."""

        return False
