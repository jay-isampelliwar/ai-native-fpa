"""Tests for the checks after parsing, against the real database, with made-up stocks, funds and saved records."""

import io
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import openpyxl
import pytest
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.enums import (
    ExpenseCategory,
    FundCategory,
    FundOptionType,
    FundPlanType,
    HoldingAssetType,
    ImportRowAction,
    ImportRowStatus,
    PaymentFrequency,
    )
from app.db.models import Expense, Holding, ImportRow, MutualFund, Stock
from app.db.session import SessionLocal
from app.features.documents.repository import DocumentRepository
from app.features.documents.schemas import AnswerIn
from app.features.documents.service import AnswerInvalid, DocumentService
from tests.support import create_user, delete_user_data


LETTERS = str.maketrans("0123456789", "ghijklmnop")


@dataclass
class Market:

    """The made-up stock and fund plans one test uses, and the tag that makes their names unique."""

    tag: str
    stock: Stock
    direct: MutualFund
    regular: MutualFund


@pytest.fixture(autouse=True)
def temp_uploads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
    ) -> None:

    """Save uploaded files to a temp folder instead of var/uploads."""

    monkeypatch.setattr(get_settings(), "UPLOAD_DIR", str(tmp_path))


@pytest.fixture
async def market() -> AsyncIterator[Market]:

    """One stock and two plans of one fund with unique names and ISINs, removed afterwards."""

    tag = uuid4().hex[:6].translate(LETTERS)
    code = uuid4().hex[:7].upper().translate(str.maketrans("ABCDEF", "GHJKLM"))

    async with SessionLocal() as session:

        stock = Stock(isin=f"INZ{code}01", symbol=f"ZQ{tag.upper()}", company_name=f"Zq{tag} Industries", is_etf=False)
        direct = fund(f"INY{code}01", f"Zq{tag} Flexi Cap Fund - Direct Plan - Growth", FundPlanType.direct)
        regular = fund(f"INY{code}02", f"Zq{tag} Flexi Cap Fund - Regular Plan - Growth", FundPlanType.regular)
        session.add_all([stock, direct, regular])
        await session.commit()

    yield Market(tag, stock, direct, regular)

    async with SessionLocal() as session:
        await session.execute(delete(Stock).where(Stock.id == stock.id))
        await session.execute(delete(MutualFund).where(MutualFund.id.in_([direct.id, regular.id])))
        await session.commit()


def fund(
    isin: str,
    name: str,
    plan: FundPlanType
    ) -> MutualFund:

    """A made-up fund plan."""

    return MutualFund(
        isin=isin,
        scheme_name=name,
        amc_name="Zq Mutual Fund",
        category=FundCategory.equity,
        plan_type=plan,
        option_type=FundOptionType.growth,
        )


@pytest.fixture
async def user_id(market: Market) -> AsyncIterator[int]:

    """A temp user, removed with all their data before the made-up market is."""

    created = await create_user()

    yield created

    await delete_user_data(created)


def workbook(
    funds: list[list],
    stocks: list[list],
    base_date: str | None = "2026-11-01"
    ) -> bytes:

    """A planner workbook with these fund and stock lines, one expense, and the plan date unless it is None."""

    book = openpyxl.Workbook()
    book.remove(book.active)

    sheets = {
        "1_Personal_Details": [
            ["Plan base date:", base_date] if base_date else ["1. Personal Details"],
            ["Role", "Name", "Date of Birth"],
            ["Primary Client", "Test User", "1990-01-15"],
            ],
        "2_Income": [["2. Income — Monthly (INR)"], ["Source", "Member 1", "Is Deduction"], ["Salary", 100000, "FALSE"]],
        "3_Expenses": [["3. Expenses — Monthly (INR)"], ["Category", "Section", "Member 1"], ["Groceries & Household", "Essential", 12000]],
        "4A_Mutual_Funds": [["Fund Name", "Type", "Folio", "Units", "Current Value", "SIP Amount"], *funds],
        "4B_Equity_Stocks": [["Stock Name", "ISIN", "Quantity", "Current Price", "Current Value"], *stocks],
        }

    for name, rows in sheets.items():

        sheet = book.create_sheet(name)

        for row in rows:
            sheet.append(row)

    buffer = io.BytesIO()
    book.save(buffer)

    return buffer.getvalue()


async def upload(
    user_id: int,
    data: bytes
    ) -> tuple[int, dict[str, ImportRow]]:

    """Upload a workbook and return the document id and its rows by the name they hold."""

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "plan.xlsx", data)

    return document.id, await rows_by_name(document.id)


async def rows_by_name(document_id: int) -> dict[str, ImportRow]:

    """A document's rows keyed by their name, security name, or table with row number."""

    async with SessionLocal() as session:
        rows = await DocumentRepository(session).rows(document_id)

    named = {}

    for row in rows:

        key = row.parsed_data.get("security_name") or row.parsed_data.get("name") or row.target_table
        named[f"{key}#{row.row_number}" if key in named else key] = row

    return named


async def answer(
    user_id: int,
    document_id: int,
    row: ImportRow,
    question_id: str,
    value: str
    ) -> dict[str, ImportRow]:

    """Answer one question and return the rows checked again."""

    async with SessionLocal() as session:
        await DocumentService(session).answer(user_id, document_id, [AnswerIn(row_id=row.id, question_id=question_id, answer=value)])

    return await rows_by_name(document_id)


async def test_exact_isin_needs_no_question(
    user_id: int,
    market: Market
    ) -> None:

    """A stock with a known ISIN is matched with no question and becomes a new holding."""

    _, rows = await upload(user_id, workbook([], [[f"ZQ{market.tag.upper()}", market.stock.isin, 10, 100, 1000]]))
    row = rows[f"ZQ{market.tag.upper()}"]

    assert row.questions == []
    assert row.resolved["instrument"]["id"] == market.stock.id
    assert row.action == ImportRowAction.create
    assert row.errors == []


async def test_unknown_isin_is_an_error(user_id: int) -> None:

    """An ISIN missing from the stock and fund lists blocks the row with an error."""

    _, rows = await upload(user_id, workbook([], [["NOPE", "INX000000019", 1, 10, 10]]))

    assert rows["NOPE"].errors and "not in the stock or fund list" in rows["NOPE"].errors[0]
    assert rows["NOPE"].action is None


async def test_fund_name_asks_with_direct_plan_first_then_answer_settles(
    user_id: int,
    market: Market
    ) -> None:

    """A fund by name is never picked silently: the question lists the Direct plan first, and the answer settles the row."""

    document_id, rows = await upload(user_id, workbook([[f"Zq{market.tag} Flexi Cap Direct Growth", "Direct Growth", "111", 10, 1000]], []))
    row = next(row for name, row in rows.items() if name.startswith(f"Zq{market.tag}"))
    asked = row.questions[0]

    assert asked["kind"] == "pick_instrument"
    assert asked["options"][0]["value"] == f"fund:{market.direct.id}"
    assert asked["options"][-1]["value"] == "none"
    assert row.action is None

    rows = await answer(user_id, document_id, row, asked["id"], f"fund:{market.direct.id}")
    row = next(row for name, row in rows.items() if name.startswith(f"Zq{market.tag}"))

    assert row.questions[0]["answer"] == f"fund:{market.direct.id}"
    assert row.resolved["instrument"]["id"] == market.direct.id
    assert row.action == ImportRowAction.create


async def test_saved_holding_without_folio_asks_if_same(
    user_id: int,
    market: Market
    ) -> None:

    """A saved holding with no folio is never assumed to be the file's folio line; saying yes makes it an update."""

    async with SessionLocal() as session:
        saved = Holding(user_id=user_id, asset_type=HoldingAssetType.stock, stock_id=market.stock.id, units=Decimal(5), as_of_date=date(2026, 1, 1))
        session.add(saved)
        await session.commit()

    symbol = f"ZQ{market.tag.upper()}"
    funds_sheet = [[symbol, None, "F-77", 10, 1000]]
    document_id, rows = await upload(user_id, workbook(funds_sheet, []))
    row = rows[symbol]
    asked = row.questions[-1]

    assert asked["kind"] == "pick_record"
    assert row.action is None

    rows = await answer(user_id, document_id, row, asked["id"], f"record:{saved.id}")
    row = rows[symbol]

    assert row.action == ImportRowAction.update
    assert row.target_record_id == saved.id
    assert row.resolved["changes"]["units"] == "5.0000"
    assert "folio_number" in row.resolved["changes"]


async def test_duplicate_lines_ask_and_skip(
    user_id: int,
    market: Market
    ) -> None:

    """The same stock twice with no folio asks about each line, and skipping one rejects only that line."""

    symbol = f"ZQ{market.tag.upper()}"
    line = [symbol, market.stock.isin, 1, 100, 100]
    document_id, rows = await upload(user_id, workbook([], [line, line]))
    first, second = rows[symbol], rows[f"{symbol}#{rows[symbol].row_number + 1}"]

    assert first.questions[0]["kind"] == "keep_duplicate"

    rows = await answer(user_id, document_id, second, f"duplicate:{second.row_number}", "skip")
    second = rows[f"{symbol}#{second.row_number}"]

    assert second.status == ImportRowStatus.rejected
    assert rows[symbol].status == ImportRowStatus.proposed

    with pytest.raises(AnswerInvalid):
        await answer(user_id, document_id, second, f"duplicate:{second.row_number}", "maybe")


async def test_value_mismatch_asks(
    user_id: int,
    market: Market
    ) -> None:

    """Units times price far from the value given raises a question."""

    symbol = f"ZQ{market.tag.upper()}"
    _, rows = await upload(user_id, workbook([], [[symbol, market.stock.isin, 10, 100, 5000]]))

    assert [item["kind"] for item in rows[symbol].questions] == ["value_mismatch"]


async def test_saved_expense_same_values_is_no_change(user_id: int) -> None:

    """An expense with the same category, name and values as a saved one is marked no change."""

    async with SessionLocal() as session:
        session.add(Expense(
            user_id=user_id,
            category=ExpenseCategory.groceries,
            name="Groceries & Household",
            amount=Decimal(12000),
            frequency=PaymentFrequency.monthly,
            is_essential=True,
            ))
        await session.commit()

    _, rows = await upload(user_id, workbook([], []))

    assert rows["Groceries & Household"].action == ImportRowAction.no_change
    assert rows["Salary"].action == ImportRowAction.create


async def test_missing_units_is_an_error(
    user_id: int,
    market: Market
    ) -> None:

    """A holding line with a value but no units is blocked until the units are filled in."""

    symbol = f"ZQ{market.tag.upper()}"
    _, rows = await upload(user_id, workbook([], [[symbol, market.stock.isin, None, 100, 1000]]))

    assert any(error.startswith("units: missing") for error in rows[symbol].errors)


async def test_name_without_space_finds_spaced_fund(
    user_id: int,
    market: Market
    ) -> None:

    """'Flexicap' in the file still offers the 'Flexi Cap' plans as choices."""

    _, rows = await upload(user_id, workbook([[f"Zq{market.tag} Flexicap Direct Growth", "Direct Growth", "222", 10, 1000]], []))
    row = next(row for name, row in rows.items() if name.startswith(f"Zq{market.tag}"))

    assert row.questions[0]["options"][0]["value"] == f"fund:{market.direct.id}"
