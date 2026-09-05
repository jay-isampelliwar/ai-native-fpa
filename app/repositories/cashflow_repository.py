"""Ownership scoped reads of the records a cash flow question needs.

This is the layer where "whose data is this" is decided, and it is decided in Python
with no model involvement. Every method takes a ``user_id`` and filters on it, so a skill
cannot widen its own access by constructing a different query - it has no query to
construct. A bug in a prompt therefore cannot become a data leak; it would have to be a
bug in this file.

Records are fetched as one bundle rather than four separate calls. A cash flow answer
quotes an evidence set, and that set is only coherent if the income, expenses, EMIs and
SIPs behind it were read at the same moment. Four independent reads can straddle a write
and produce a surplus figure that never existed.

Inactive records are excluded on read rather than filtered by callers. A closed loan or a
stopped SIP still exists for history and audit, but including it in this month's surplus
would be wrong, and leaving that judgement to each skill guarantees two skills eventually
disagree.

Phase 1 is backed by a seeded dictionary so the graph can be exercised end to end before
the database exists. ``CashflowRepository`` is the interface the skills depend on, so the
SQL implementation replaces ``InMemoryCashflowRepository`` without a skill changing.
"""

from datetime import date
from decimal import Decimal
from typing import Protocol

from app.models.finance import (
    CashflowRecords,
    EmiRecord,
    ExpenseRecord,
    Frequency,
    IncomeRecord,
    SipRecord,
)


class CashflowRepository(Protocol):

    """The read interface every cash flow skill depends on, independent of where records are stored."""

    async def get_cashflow_records(self, user_id: int) -> CashflowRecords: ...


SEEDED_RECORDS: dict[int, CashflowRecords] = {
    1: CashflowRecords(
        income=[
            IncomeRecord(
                id="inc_1",
                user_id=1,
                label="Salary",
                amount=Decimal("150000"),
                frequency=Frequency.MONTHLY,
                source="salary",
            ),
            IncomeRecord(
                id="inc_2",
                user_id=1,
                label="Annual bonus",
                amount=Decimal("240000"),
                frequency=Frequency.ANNUAL,
                source="bonus",
            ),
        ],
        expenses=[
            ExpenseRecord(
                id="exp_1",
                user_id=1,
                label="Household",
                amount=Decimal("55000"),
                category="living",
            ),
            ExpenseRecord(
                id="exp_2",
                user_id=1,
                label="Term insurance premium",
                amount=Decimal("24000"),
                frequency=Frequency.ANNUAL,
                category="insurance",
            ),
        ],
        emis=[
            EmiRecord(
                id="emi_1",
                user_id=1,
                label="Home loan",
                amount=Decimal("42000"),
                liability_id="liab_1",
                interest_rate_percent=Decimal("8.65"),
                remaining_months=168,
            ),
        ],
        sips=[
            SipRecord(
                id="sip_1",
                user_id=1,
                label="Flexi cap SIP",
                amount=Decimal("10000"),
                scheme_name="Parag Parikh Flexi Cap",
                folio_id="folio_9931",
                next_debit_on=date(2026, 10, 5),
                linked_goal_id="goal_1",
            ),
        ],
    ),
}


class InMemoryCashflowRepository:

    """Phase 1 repository over seeded records, filtering by owner exactly as the SQL one will."""

    def __init__(self, records: dict[int, CashflowRecords] | None = None) -> None:

        """Hold the seeded record set, allowing tests to supply their own fixture."""

        self._records = records if records is not None else SEEDED_RECORDS

    async def get_cashflow_records(self, user_id: int) -> CashflowRecords:

        """Return this user's active income, expenses, EMIs and SIPs as one consistent bundle."""

        bundle = self._records.get(user_id)

        if bundle is None:
            return CashflowRecords()

        return CashflowRecords(
            income=[record for record in bundle.income if record.active and record.user_id == user_id],
            expenses=[record for record in bundle.expenses if record.active and record.user_id == user_id],
            emis=[record for record in bundle.emis if record.active and record.user_id == user_id],
            sips=[record for record in bundle.sips if record.active and record.user_id == user_id],
        )


cashflow_repository: CashflowRepository = InMemoryCashflowRepository()
