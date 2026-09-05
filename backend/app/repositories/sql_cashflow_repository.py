"""The SQL implementation of the cash flow read, replacing the seeded dictionary.

Nothing above this file changes when it is swapped in. The skill depends on the
``CashflowRepository`` protocol, so the only difference between Phase 1 and Phase 2 is
which object satisfies it - which is the point of having written the protocol first.

All four record types are fetched inside one session and therefore one transaction
snapshot. That is not an optimisation, it is a correctness requirement: four independent
reads can straddle a write and produce a surplus figure that never existed at any moment.

Ownership is applied as a ``WHERE user_id`` on every query, and the active filter with it.
A closed loan or a stopped SIP still exists for history and audit, but counting it in this
month's committed outflow would be wrong, and leaving that judgement to callers guarantees
two skills eventually disagree about the same month.

Rows are converted to the domain models rather than returned as ORM objects. A detached
SQLAlchemy instance that lazy loads on attribute access is a database call hiding inside
what looks like a field read, and inside an agent loop that is a call nobody budgeted for.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_scope
from app.models.finance import (
    CashflowRecords,
    EmiRecord,
    ExpenseRecord,
    IncomeRecord,
    SipRecord,
)
from app.models.finance import SipStatus
from app.models.orm.cashflow import ExpenseRecordRow, IncomeRecordRow
from app.models.orm.credit import EmiRecordRow, SipRecordRow


class SqlCashflowRepository:

    """Reads one user's recurring income, expenses, EMIs and SIPs from PostgreSQL in one snapshot."""

    def __init__(self, session: AsyncSession | None = None) -> None:

        """Take a session to reuse, or open one per call when running outside a unit of work."""

        self._session = session

    async def get_cashflow_records(self, user_id: int) -> CashflowRecords:

        """Return this user's active cash flow records, read together so the evidence set is coherent."""

        if self._session is not None:
            return await self._read(self._session, user_id)

        async with session_scope() as session:
            return await self._read(session, user_id)

    async def _read(self, session: AsyncSession, user_id: int) -> CashflowRecords:

        """Run the four owner scoped queries and convert every row to its domain model."""

        income = await session.scalars(
            select(IncomeRecordRow).where(
                IncomeRecordRow.user_id == user_id,
                IncomeRecordRow.active.is_(True),
            )
        )

        expenses = await session.scalars(
            select(ExpenseRecordRow).where(
                ExpenseRecordRow.user_id == user_id,
                ExpenseRecordRow.active.is_(True),
            )
        )

        emis = await session.scalars(
            select(EmiRecordRow).where(
                EmiRecordRow.user_id == user_id,
                EmiRecordRow.active.is_(True),
            )
        )

        sips = await session.scalars(
            select(SipRecordRow).where(
                SipRecordRow.user_id == user_id,
                SipRecordRow.status == SipStatus.ACTIVE,
            )
        )

        return CashflowRecords(
            income=[
                IncomeRecord(
                    id=row.id,
                    user_id=row.user_id,
                    label=row.label,
                    amount=row.amount,
                    frequency=row.frequency,
                    active=row.active,
                    source=row.source,
                )
                for row in income
            ],
            expenses=[
                ExpenseRecord(
                    id=row.id,
                    user_id=row.user_id,
                    label=row.label,
                    amount=row.amount,
                    frequency=row.frequency,
                    active=row.active,
                    category=row.category,
                )
                for row in expenses
            ],
            emis=[
                EmiRecord(
                    id=row.id,
                    user_id=row.user_id,
                    label=row.label,
                    amount=row.amount,
                    frequency=row.frequency,
                    active=row.active,
                    liability_id=row.liability_id,
                    interest_rate_percent=row.interest_rate_percent,
                    remaining_months=row.remaining_months,
                )
                for row in emis
            ],
            sips=[
                SipRecord(
                    id=row.id,
                    user_id=row.user_id,
                    label=row.scheme_name,
                    amount=row.amount,
                    frequency=row.frequency,
                    active=row.status == SipStatus.ACTIVE,
                    scheme_name=row.scheme_name,
                    folio_id=row.folio_id,
                    next_debit_on=row.next_debit_on,
                    linked_goal_id=row.linked_goal_id,
                )
                for row in sips
            ],
        )
