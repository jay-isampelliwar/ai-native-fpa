"""The same repository behaviour asserted against both backends, so they cannot drift apart.

Each test is parametrised over the in-memory and SQL implementations and asserts identical
results. That is the whole point: the skills were written and tested against fixtures, and
this file is what makes "the SQL version behaves the same" a checked claim rather than an
assumption. A difference in filtering, ordering or rounding fails here rather than in
production.

The SQL cases are skipped when PostgreSQL is unreachable, so the suite still runs offline.
When it is reachable they run against the seeded development data, which is the same data
the fixtures hold - that equivalence is what makes the comparison meaningful.

``test_ownership_is_enforced_identically`` is the one that matters. Every other difference
between the backends would produce a worse answer; a difference in this one produces one
person seeing another person's records.

Money assertions compare ``Decimal`` values rather than strings, because the two backends
legitimately differ in trailing zeros - the database returns ``NUMERIC(14,2)`` and the
fixtures hold whatever was typed. Comparing numerically asserts what actually matters.
"""

from decimal import Decimal

import pytest

from app.repositories.cashflow_repository import InMemoryCashflowRepository
from app.repositories.expense_repository import InMemoryExpenseRepository
from app.repositories.sql_cashflow_repository import SqlCashflowRepository
from app.repositories.sql_expense_repository import SqlExpenseRepository


async def postgres_available() -> bool:

    """Report whether the configured database can be reached, so SQL cases can skip cleanly."""

    try:
        from sqlalchemy import text

        from app.db.session import session_scope

        async with session_scope() as session:
            await session.execute(text("SELECT 1"))

        return True

    except Exception:
        return False


@pytest.fixture(params=["memory", "sql"])
async def cashflow_repository(request):

    """Yield each cash flow backend in turn, skipping SQL when no database is reachable."""

    if request.param == "memory":
        return InMemoryCashflowRepository()

    if not await postgres_available():
        pytest.skip("postgres is not reachable")

    return SqlCashflowRepository()


@pytest.fixture(params=["memory", "sql"])
async def expense_repository(request):

    """Yield each expense backend in turn, skipping SQL when no database is reachable."""

    if request.param == "memory":
        return InMemoryExpenseRepository()

    if not await postgres_available():
        pytest.skip("postgres is not reachable")

    return SqlExpenseRepository()


async def test_cashflow_returns_the_same_evidence_set(cashflow_repository):

    """Both backends return the same six records for the seeded user, in the same grouping."""

    records = await cashflow_repository.get_cashflow_records(1)

    assert sorted(records.evidence_ids) == ["emi_1", "exp_1", "exp_2", "inc_1", "inc_2", "sip_1"]
    assert len(records.income) == 2
    assert len(records.emis) == 1
    assert len(records.sips) == 1


async def test_cashflow_amounts_and_frequencies_match(cashflow_repository):

    """The annual bonus normalises to the same monthly figure whichever backend returned it."""

    records = await cashflow_repository.get_cashflow_records(1)

    bonus = next(record for record in records.income if record.id == "inc_2")

    assert bonus.amount == Decimal("240000")
    assert bonus.monthly_amount == Decimal("20000.00")


async def test_ownership_is_enforced_identically(cashflow_repository):

    """A user with no records gets an empty bundle rather than someone else's."""

    records = await cashflow_repository.get_cashflow_records(2)

    assert records.evidence_ids == []


async def test_category_totals_agree(expense_repository):

    """August totals are identical across backends, including the ordering by size."""

    totals = await expense_repository.category_totals(1, 2026, 8)

    assert list(totals)[0] == "shopping"
    assert totals["shopping"] == Decimal("32000")
    assert totals["travel"] == Decimal("14200")
    assert totals["dining"] == Decimal("11750")


async def test_transactions_are_newest_first_and_owner_scoped(expense_repository):

    """Both backends order by date descending and never return another user's transactions."""

    rows = await expense_repository.list_transactions(1, year=2026, month=8)

    assert [row.id for row in rows][:3] == ["txn_12", "txn_11", "txn_10"]
    assert all(row.user_id == 1 for row in rows)
    assert "txn_13" not in [row.id for row in rows]


async def test_category_filter_agrees(expense_repository):

    """Filtering to one category returns the same single row from either backend."""

    rows = await expense_repository.list_transactions(1, year=2026, month=8, category="shopping")

    assert [row.id for row in rows] == ["txn_10"]
    assert rows[0].merchant == "Croma"


async def test_the_injected_description_survives_storage(expense_repository):

    """The instruction bearing description is stored and returned verbatim, as untrusted data."""

    rows = await expense_repository.list_transactions(1, year=2026, month=8, category="subscriptions")

    assert rows[0].id == "txn_12"
    assert "ignore previous instructions" in rows[0].description


async def test_limits_are_applied_by_both_backends(expense_repository):

    """A requested limit is honoured, so an agent cannot pull an unbounded page of spending."""

    rows = await expense_repository.list_transactions(1, limit=3)

    assert len(rows) == 3
