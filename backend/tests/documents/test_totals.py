"""Tests for the totals check: total lines kept out of rows, labelled totals, opening and closing balance, and running balance."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models import LayoutMapping
from app.db.session import SessionLocal
from app.features.documents.layouts import layout_of, parse_mapped
from app.features.documents.reader import file_kind, read_file
from app.features.documents.repository import DocumentRepository
from app.features.documents.schemas import RowEdit
from app.features.documents.service import DocumentService, EditInvalid, NothingToApprove
from app.features.documents.totals import check_totals, is_summary_line, mismatch_key
from app.features.documents.reader import Cell
from tests.documents.test_service import temp_uploads, user_id


__all__ = ["temp_uploads", "user_id"]

LETTERS = str.maketrans("0123456789", "ghijklmnop")

COLUMNS = {"Date": "txn_date", "Narration": "description", "Withdrawal": "debit_amount", "Deposit": "credit_amount", "Balance": "balance"}


def statement(
    closing: str,
    balances: tuple[str, str, str] = ("9550.00", "104550.00", "104300.00"),
    narration: str = "Narration"
    ) -> bytes:

    """A bank statement with an opening balance, three lines with a running balance, and a closing balance."""

    first, second, third = balances

    return (
        "Account,Test Person\n"
        "Opening Balance,10000.00\n"
        "\n"
        f"Date,{narration},Withdrawal,Deposit,Balance\n"
        f"01/10/2026,UPI-SWIGGY,450.00,,{first}\n"
        f"02/10/2026,SALARY,,95000.00,{second}\n"
        f"03/10/2026,UPI-METRO,250.00,,{third}\n"
        f"Closing Balance,{closing}\n"
        ).encode()


def mapped(data: bytes):

    """The statement read with the bank column plan."""

    sheet = read_file(file_kind("bank.csv", data), data)[0]
    layout = layout_of(sheet)

    return parse_mapped(sheet, layout.headers, "transactions", COLUMNS)


def rows_of(data: bytes) -> dict[str, list[dict]]:

    """The parsed rows as values, grouped by sheet, the way the check reads them."""

    result = mapped(data)

    return {"CSV": [{**row.data, "_line": row.source["row"]} for row in result.rows]}


def test_summary_lines_are_kept_out_of_rows() -> None:

    """Opening and closing balance lines are totals to check, not transactions."""

    result = mapped(statement("104300.00"))

    assert len(result.rows) == 3
    assert {item["metric"] for item in result.printed} == {"opening_balance", "closing_balance"}


def test_total_line_needs_an_amount_and_a_total_word() -> None:

    """A 'Total' line with amounts is a total; a fund named 'Total Return Fund' or a bare 'Total' heading is not."""

    assert is_summary_line([Cell("Grand Total", "A9"), Cell(15000, "E9")])
    assert not is_summary_line([Cell("Total Return Fund", "A9"), Cell(15000, "E9")])
    assert not is_summary_line([Cell("Total", "A9")])


def test_matching_statement_passes() -> None:

    """Opening plus credits minus debits equals closing, and every running balance follows the line before it."""

    checks = check_totals(rows_of(statement("104300.00")), mapped(statement("104300.00")).printed)

    assert checks and all(item["ok"] for item in checks)
    assert mismatch_key(checks) is None


def test_wrong_closing_balance_is_caught() -> None:

    """A closing balance ₹100 away from the rows is a mismatch; within ₹1 is not."""

    far = check_totals(rows_of(statement("104400.00")), mapped(statement("104400.00")).printed)
    near = check_totals(rows_of(statement("104300.80")), mapped(statement("104300.80")).printed)

    closing = next(item for item in far if item["label"].startswith("Opening balance"))

    assert not closing["ok"] and closing["difference"] == "-100.00"
    assert all(item["ok"] for item in near if item["label"].startswith("Opening balance"))


def test_running_balance_names_the_line_that_breaks() -> None:

    """A balance that does not follow the line before it is reported at that line."""

    data = statement("104300.00", balances=("9550.00", "104000.00", "103750.00"))
    checks = check_totals(rows_of(data), mapped(data).printed)
    broken = next(item for item in checks if item["label"].startswith("Running balance breaks"))

    assert not broken["ok"]
    assert "line 6" in broken["label"]


def test_newest_first_running_balance_passes() -> None:

    """A statement listed newest first still checks line by line."""

    rows = [
        {"amount": "250.00", "direction": "outflow", "balance": "104300.00"},
        {"amount": "95000.00", "direction": "inflow", "balance": "104550.00"},
        {"amount": "450.00", "direction": "outflow", "balance": "9550.00"},
        ]

    assert all(item["ok"] for item in check_totals({"CSV": rows}, []))


def test_holding_column_total_and_present_value() -> None:

    """A total line's value column and a present value label are both checked against the holding rows."""

    rows = [{"units": "10", "current_price": "100", "current_value": "1000.00"}, {"units": "5", "current_price": "200", "current_value": "1000.00"}]
    printed = [
        {"sheet": "S", "metric": "column_total", "field": "current_value", "value": "2000.00", "ref": "E9"},
        {"sheet": "S", "metric": "present_value", "field": None, "value": "2500.00", "ref": "B2"},
        ]
    checks = {item["label"]: item for item in check_totals({"S": rows}, printed)}

    assert checks["Total of current value"]["ok"]
    assert not checks["Present value"]["ok"]


@pytest.fixture
async def bank_plan() -> AsyncIterator[str]:

    """A confirmed bank plan for headers unique to this test, so no model is asked, removed afterwards."""

    narration = f"Narration {uuid4().hex[:6].translate(LETTERS)}"
    data = statement("104300.00", narration=narration)
    sheet = read_file(".csv", data)[0]
    layout = layout_of(sheet)
    columns = {**COLUMNS, narration: "description"}
    columns.pop("Narration")

    async with SessionLocal() as session:
        await DocumentRepository(session).confirm(layout.fingerprint, layout.headers, "transactions", columns, None)
        await session.commit()

    yield narration

    async with SessionLocal() as session:
        await session.execute(delete(LayoutMapping).where(LayoutMapping.fingerprint == layout.fingerprint))
        await session.commit()


async def test_mismatch_blocks_import_until_you_accept_or_fix(
    user_id: int,
    bank_plan: str
    ) -> None:

    """A wrong closing balance blocks the import; Import anyway lets it through, and a changed mismatch asks again."""

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "bank.csv", statement("104400.00", narration=bank_plan))
        rows = await DocumentRepository(session).rows(document.id)

    assert document.summary["totals_blocked"] is True

    for row in rows:

        async with SessionLocal() as session:
            await DocumentService(session).edit(user_id, document.id, row.id, RowEdit(changes={"category": "other"}))

    async with SessionLocal() as session:

        with pytest.raises(NothingToApprove):
            await DocumentService(session).approve(user_id, document.id)

    async with SessionLocal() as session:
        document = await DocumentService(session).accept_totals(user_id, document.id)

    assert document.summary["totals_blocked"] is False

    async with SessionLocal() as session:
        await DocumentService(session).edit(user_id, document.id, rows[0].id, RowEdit(changes={"amount": "500.00"}))
        document = await DocumentService(session).get(user_id, document.id)

    assert document.summary["totals_blocked"] is True

    async with SessionLocal() as session:
        await DocumentService(session).edit(user_id, document.id, rows[0].id, RowEdit(changes={"amount": "350.00"}))
        document = await DocumentService(session).get(user_id, document.id)

    checks = {item["label"].split(":")[0]: item for item in document.summary["totals"]}

    assert checks["Opening balance + credits − debits = closing balance"]["ok"]
    assert not checks["Running balance breaks at line 5"]["ok"]
    assert document.summary["totals_blocked"] is True


async def test_accept_needs_a_mismatch(
    user_id: int,
    bank_plan: str
    ) -> None:

    """There is nothing to accept when the totals already match."""

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "bank.csv", statement("104300.00", narration=bank_plan))

    assert document.summary["totals_blocked"] is False

    async with SessionLocal() as session:

        with pytest.raises(EditInvalid):
            await DocumentService(session).accept_totals(user_id, document.id)
