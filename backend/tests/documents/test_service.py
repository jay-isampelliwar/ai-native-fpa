"""Tests for the upload flow against the real database, with the mapping model faked and files saved to a temp folder."""

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.enums import DocumentStatus
from app.db.models import LayoutMapping
from app.db.session import SessionLocal
from app.features.documents import service as document_service
from app.features.documents.layouts import ColumnChoice, SheetLayout, SheetMapping, fingerprint
from app.features.documents.repository import DocumentRepository
from app.features.documents.schemas import SheetChoice
from app.features.documents.service import DocumentService, MappingInvalid
from tests.documents.test_planner_workbook import build_workbook
from tests.support import create_user, delete_user_data


asked: list[str] = []


@pytest.fixture(autouse=True)
def temp_uploads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
    ) -> None:

    """Save uploaded files to a temp folder instead of var/uploads."""

    monkeypatch.setattr(get_settings(), "UPLOAD_DIR", str(tmp_path))


@pytest.fixture(autouse=True)
def fake_model(monkeypatch: pytest.MonkeyPatch) -> None:

    """Answer every mapping request with a bank statement mapping, and count the calls."""

    asked.clear()

    async def propose(layout: SheetLayout) -> SheetMapping:

        """Map the date, narration and withdrawal columns, the way the model would."""

        asked.append(layout.sheet.name)

        return SheetMapping(
            target_table="transactions",
            columns=[
                ColumnChoice(header=layout.headers[0], field="txn_date"),
                ColumnChoice(header=layout.headers[1], field="description"),
                ColumnChoice(header=layout.headers[2], field="debit_amount"),
                ],
            reason="A bank statement",
            )

    monkeypatch.setattr(document_service, "propose_mapping", propose)


@pytest.fixture
async def user_id() -> AsyncIterator[int]:

    """A temp user, removed with their documents afterwards."""

    created = await create_user()

    yield created

    await delete_user_data(created)


@pytest.fixture
def bank_headers() -> list[str]:

    """Headers unique to this test in letters only, so its shared mapping never meets another test's."""

    tag = uuid4().hex[:8].translate(str.maketrans("0123456789", "ghijklmnop"))

    return ["Date", f"Narration {tag}", "Withdrawal Amt."]


@pytest.fixture(autouse=True)
async def drop_test_mappings() -> AsyncIterator[None]:

    """Remove the layout mappings these tests create."""

    yield

    async with SessionLocal() as session:
        await session.execute(delete(LayoutMapping).where(LayoutMapping.reason == "A bank statement"))
        await session.commit()


def bank_csv(
    headers: list[str],
    amount: str
    ) -> bytes:

    """A small bank statement CSV with one spend line."""

    return f"{','.join(headers)}\n01/10/2026,UPI-TEST,{amount}\n".encode()


async def test_planner_upload_parses_and_repeat_is_duplicate(user_id: int) -> None:

    """A planner workbook is parsed into rows; the same file again returns the same document without parsing twice."""

    data = build_workbook()

    async with SessionLocal() as session:
        document, duplicate = await DocumentService(session).upload(user_id, "plan.xlsx", data)
        rows = await DocumentRepository(session).rows(document.id)

    assert not duplicate
    assert document.status == DocumentStatus.parsed
    assert document.family == "planner_workbook"
    assert document.summary["row_count"] == len(rows) > 0
    assert [row.row_number for row in rows] == list(range(1, len(rows) + 1))

    sip = next(row for row in rows if row.target_table == "sip_plans")
    holding = next(row for row in rows if row.row_number == sip.parsed_data["holding_row_number"])

    assert holding.target_table == "holdings"

    async with SessionLocal() as session:
        again, duplicate = await DocumentService(session).upload(user_id, "plan copy.xlsx", data)

    assert duplicate
    assert again.id == document.id
    assert not asked


async def test_unknown_file_is_read_at_once_with_the_model_plan(
    user_id: int,
    bank_headers: list[str]
    ) -> None:

    """An unknown CSV is read straight away when the model's plan passes the checks, the plan is shown, and the next file of that shape skips the model."""

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "bank.csv", bank_csv(bank_headers, "450.00"))
        rows = await DocumentRepository(session).rows(document.id)

    assert document.status == DocumentStatus.parsed
    assert document.summary["plans"][0]["fingerprint"] == fingerprint(bank_headers)
    assert rows[0].parsed_data == {"txn_date": "2026-10-01", "description": "UPI-TEST", "amount": "450.00", "direction": "outflow"}
    assert rows[0].source["cells"]["debit_amount"] == "C2"
    assert asked == ["CSV"]

    async with SessionLocal() as session:
        second, _ = await DocumentService(session).upload(user_id, "bank2.csv", bank_csv(bank_headers, "99.00"))

    assert second.status == DocumentStatus.parsed
    assert asked == ["CSV"]


async def test_changing_columns_reads_the_file_again(
    user_id: int,
    bank_headers: list[str]
    ) -> None:

    """Changing a sheet's columns saves the new plan and reads the file again with it."""

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "bank.csv", bank_csv(bank_headers, "450.00"))

    columns = {bank_headers[0]: "txn_date", bank_headers[2]: "debit_amount"}

    async with SessionLocal() as session:
        document = await DocumentService(session).confirm_mapping(user_id, document.id, [SheetChoice(sheet="CSV", target_table="transactions", columns=columns)])
        rows = await DocumentRepository(session).rows(document.id)

    assert "description" not in rows[0].parsed_data
    assert document.summary["plans"][0]["confirmed_at"] is not None


async def test_plan_failing_checks_waits_for_columns(
    user_id: int,
    bank_headers: list[str],
    monkeypatch: pytest.MonkeyPatch
    ) -> None:

    """A plan with no amount column fails the checks, so the file waits for the user to pick columns."""

    async def weak(layout: SheetLayout) -> SheetMapping:

        """Map only the date, which cannot make a row."""

        return SheetMapping(target_table="transactions", columns=[ColumnChoice(header=layout.headers[0], field="txn_date")], reason="A bank statement")

    monkeypatch.setattr(document_service, "propose_mapping", weak)

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "bank.csv", bank_csv(bank_headers, "450.00"))

    assert document.status == DocumentStatus.needs_mapping
    assert document.summary["pending_mappings"][0]["errors"]


async def test_bad_mapping_is_refused(
    user_id: int,
    bank_headers: list[str]
    ) -> None:

    """A plan naming a field the table does not have is refused, and the document stays as it was."""

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "bank.csv", bank_csv(bank_headers, "10.00"))

    choice = SheetChoice(sheet="CSV", target_table="transactions", columns={"Date": "not_a_field"})

    async with SessionLocal() as session:

        with pytest.raises(MappingInvalid):
            await DocumentService(session).confirm_mapping(user_id, document.id, [choice])

        reloaded = await DocumentService(session).get(user_id, document.id)

    assert reloaded.status == DocumentStatus.parsed


async def test_broken_file_fails_with_reason(user_id: int) -> None:

    """A damaged workbook is saved as failed with a plain reason, and no rows."""

    data = b"PK\x03\x04 not really a workbook"

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "broken.xlsx", data)
        rows = await DocumentRepository(session).rows(document.id)

    assert document.status == DocumentStatus.failed
    assert "could not be opened" in document.error_message
    assert rows == []


async def test_file_with_no_rows_fails(user_id: int) -> None:

    """A file with nothing to import is marked failed with a plain reason, keeping its sheet notes."""

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "blank.csv", b"just one line of text\n")

    assert document.status == DocumentStatus.failed
    assert "No records" in document.error_message
    assert document.summary["sheets"][0]["sheet"] == "CSV"
