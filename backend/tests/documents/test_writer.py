"""Tests for editing rows, approving an import into the record tables, and undoing it, against the real database."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import DocumentStatus, ImportRowAction, ImportRowStatus
from app.db.models import Expense, Holding, IncomeSource, SipPlan, User
from app.db.session import SessionLocal
from app.features.documents.schemas import RowEdit
from app.features.documents.service import DocumentService, EditInvalid, NothingToUndo
from app.features.documents.writer import UndoBlocked
from tests.documents.test_checks import Market, market, rows_by_name, temp_uploads, upload, user_id, workbook


__all__ = ["market", "temp_uploads", "user_id"]


def stock_line(
    market: Market,
    units: object = 10,
    value: object = 1000
    ) -> list[object]:

    """One line for the made-up stock, priced so units times price equals the value."""

    return [f"ZQ{market.tag.upper()}", market.stock.isin, units, 100, value]


async def approve(
    user_id: int,
    document_id: int
    ) -> dict[str, int]:

    """Approve the document's ready rows."""

    async with SessionLocal() as session:
        return await DocumentService(session).approve(user_id, document_id)


async def edit(
    user_id: int,
    document_id: int,
    row_id: int,
    **body: object
    ) -> None:

    """Edit one row."""

    async with SessionLocal() as session:
        await DocumentService(session).edit(user_id, document_id, row_id, RowEdit(**body))


async def saved(
    model: type,
    user_id: int
    ) -> list:

    """The user's saved records of one table."""

    async with SessionLocal() as session:
        return list(await session.scalars(select(model).where(model.user_id == user_id)))


async def test_approve_writes_ready_rows_with_file_values(
    user_id: int,
    market: Market
    ) -> None:

    """Approving writes the stock, income and expense, keeps the file's value and plan date, and marks each row written."""

    document_id, rows = await upload(user_id, workbook([], [stock_line(market)]))
    outcome = await approve(user_id, document_id)
    holdings = await saved(Holding, user_id)
    rows = await rows_by_name(document_id)

    assert outcome["failed"] == 0 and outcome["written"] >= 3
    assert len(holdings) == 1
    assert holdings[0].current_value == Decimal("1000.00")
    assert holdings[0].as_of_date.isoformat() == "2026-11-01"
    assert [income.name for income in await saved(IncomeSource, user_id)] == ["Salary"]
    assert len(await saved(Expense, user_id)) == 1
    assert rows[f"ZQ{market.tag.upper()}"].status == ImportRowStatus.written
    assert rows[f"ZQ{market.tag.upper()}"].target_record_id == holdings[0].id
    assert rows[f"ZQ{market.tag.upper()}"].resolved["written"]["units"] == "10.0000"


async def test_one_failed_row_keeps_the_rest(
    user_id: int,
    market: Market,
    monkeypatch: pytest.MonkeyPatch
    ) -> None:

    """A row the service refuses is marked failed with the reason, and the other rows are still written."""

    document_id, _ = await upload(user_id, workbook([], [stock_line(market)]))

    async def refuse(*args: object) -> None:

        """Refuse every income, the way a domain service refuses a bad one."""

        from app.features.records.exceptions import RecordError

        raise RecordError("income refused for the test")

    monkeypatch.setitem(__import__("app.features.documents.writer", fromlist=["ADDERS"]).ADDERS, "income_sources", refuse)

    outcome = await approve(user_id, document_id)
    rows = await rows_by_name(document_id)

    assert outcome["failed"] == 1
    assert rows["Salary"].status == ImportRowStatus.failed
    assert "income refused for the test" in rows["Salary"].errors[0]
    assert len(await saved(Holding, user_id)) == 1
    assert await saved(IncomeSource, user_id) == []


async def test_edit_fills_missing_units_and_refuses_bad_values(
    user_id: int,
    market: Market
    ) -> None:

    """A row missing units is blocked until the units are typed in; text that is not a number is refused."""

    document_id, rows = await upload(user_id, workbook([], [stock_line(market, units=None)]))
    row = rows[f"ZQ{market.tag.upper()}"]

    assert any(error.startswith("units") for error in row.errors)

    with pytest.raises(EditInvalid):
        await edit(user_id, document_id, row.id, changes={"units": "ten"})

    with pytest.raises(EditInvalid):
        await edit(user_id, document_id, row.id, changes={"colour": "blue"})

    await edit(user_id, document_id, row.id, changes={"units": "10"})
    row = (await rows_by_name(document_id))[f"ZQ{market.tag.upper()}"]

    assert row.errors == []
    assert row.parsed_data.get("units") is None
    assert row.edited_data["units"] == "10.0000"


async def test_picking_a_fund_closes_its_question(
    user_id: int,
    market: Market
    ) -> None:

    """Picking the fund from the search sets it and removes the name question."""

    document_id, rows = await upload(user_id, workbook([[f"Zq{market.tag} Flexi Cap Direct Growth", "Direct Growth", "333", 10, 1000]], []))
    row = next(row for name, row in rows.items() if name.startswith(f"Zq{market.tag}"))

    assert row.questions

    await edit(user_id, document_id, row.id, instrument=f"fund:{market.regular.id}")
    row = next(row for name, row in (await rows_by_name(document_id)).items() if name.startswith(f"Zq{market.tag}"))

    assert row.questions == []
    assert row.resolved["instrument"]["id"] == market.regular.id
    assert row.action == ImportRowAction.create


async def test_sip_written_against_its_new_holding(
    user_id: int,
    market: Market
    ) -> None:

    """A SIP row waits for its day and start date, then is saved pointing at the holding written in the same approval."""

    document_id, rows = await upload(user_id, workbook([[f"ZQ{market.tag.upper()}", None, "444", 10, 1000, 2500]], []))
    sip = rows["sip_plans"]

    assert sip.action == ImportRowAction.create
    assert sip.errors

    await edit(user_id, document_id, sip.id, changes={"sip_day": 5, "start_date": "2026-01-05"})
    outcome = await approve(user_id, document_id)
    plans = await saved(SipPlan, user_id)
    holdings = await saved(Holding, user_id)

    assert outcome["failed"] == 0
    assert len(plans) == 1
    assert plans[0].holding_id == holdings[0].id
    assert plans[0].amount == Decimal("2500.00")


async def test_undo_removes_and_puts_back(user_id: int) -> None:

    """Undo removes the rows the import added and puts the profile back as it was."""

    async with SessionLocal() as session:
        before = (await session.get(User, user_id)).date_of_birth

    document_id, _ = await upload(user_id, workbook([], []))
    await approve(user_id, document_id)

    async with SessionLocal() as session:
        assert (await session.get(User, user_id)).date_of_birth.isoformat() == "1990-01-15"
        undone = await DocumentService(session).undo(user_id, document_id)
        document = await DocumentService(session).get(user_id, document_id)

    async with SessionLocal() as session:
        after = (await session.get(User, user_id)).date_of_birth

    assert undone == 3
    assert after == before
    assert await saved(IncomeSource, user_id) == []
    assert await saved(Expense, user_id) == []
    assert document.status == DocumentStatus.rejected

    async with SessionLocal() as session:

        with pytest.raises(NothingToUndo):
            await DocumentService(session).undo(user_id, document_id)


async def test_undo_stops_when_you_changed_a_record(user_id: int) -> None:

    """Undo changes nothing when a record the import wrote was changed afterwards."""

    document_id, _ = await upload(user_id, workbook([], []))
    await approve(user_id, document_id)

    async with SessionLocal() as session:
        income = await session.scalar(select(IncomeSource).where(IncomeSource.user_id == user_id))
        income.amount = Decimal("120000")
        await session.commit()

    async with SessionLocal() as session:

        with pytest.raises(UndoBlocked) as blocked:
            await DocumentService(session).undo(user_id, document_id)

    assert "amount" in blocked.value.reasons[0]
    assert len(await saved(Expense, user_id)) == 1


async def test_no_change_rows_are_done_without_writing(user_id: int) -> None:

    """A second import of the same values marks rows no change and writes nothing new."""

    first, _ = await upload(user_id, workbook([], []))
    await approve(user_id, first)

    second, _ = await upload(user_id, workbook([], [["NOPE", "INX000000019", 1, 10, 10]]))
    outcome = await approve(user_id, second)

    assert outcome["written"] == 0
    assert outcome["no_change"] == 3
    assert len(await saved(IncomeSource, user_id)) == 1


async def test_one_date_for_every_undated_row(
    user_id: int,
    market: Market
    ) -> None:

    """Rows with no as-of date get the chosen date in one step, and a future date is refused."""

    from datetime import date, timedelta

    document_id, rows = await upload(user_id, workbook([], [stock_line(market)], base_date=None))
    row = rows[f"ZQ{market.tag.upper()}"]

    assert any(error.startswith("as_of_date") for error in row.errors)

    async with SessionLocal() as session:

        with pytest.raises(EditInvalid):
            await DocumentService(session).set_as_of_date(user_id, document_id, date.today() + timedelta(days=1))

    async with SessionLocal() as session:
        await DocumentService(session).set_as_of_date(user_id, document_id, date(2026, 10, 31))

    row = (await rows_by_name(document_id))[f"ZQ{market.tag.upper()}"]

    assert row.edited_data["as_of_date"] == "2026-10-31"
    assert not any(error.startswith("as_of_date") for error in row.errors)


async def test_removed_row_is_never_written_and_can_come_back(
    user_id: int,
    market: Market
    ) -> None:

    """A removed row stays out of the import and its checks, and bringing it back makes it ready again."""

    document_id, rows = await upload(user_id, workbook([], [stock_line(market)]))
    row = rows[f"ZQ{market.tag.upper()}"]

    async with SessionLocal() as session:
        await DocumentService(session).remove_row(user_id, document_id, row.id, True)

    outcome = await approve(user_id, document_id)

    assert await saved(Holding, user_id) == []
    assert outcome["written"] >= 1

    removed = (await rows_by_name(document_id))[f"ZQ{market.tag.upper()}"]

    assert removed.status == ImportRowStatus.rejected
    assert removed.resolved["removed"] is True

    async with SessionLocal() as session:
        await DocumentService(session).remove_row(user_id, document_id, row.id, False)

    back = (await rows_by_name(document_id))[f"ZQ{market.tag.upper()}"]

    assert back.status == ImportRowStatus.proposed
    assert back.action == ImportRowAction.create

    second = await approve(user_id, document_id)

    assert second["written"] == 1
    assert len(await saved(Holding, user_id)) == 1
