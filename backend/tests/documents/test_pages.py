"""Tests for PDFs and photos: tables read by code, other pages read by the model only after the user's OK, and locked PDFs."""

import io

import pytest
from PIL import Image

from app.db.enums import DocumentStatus
from app.db.session import SessionLocal
from app.features.documents import pages as page_module
from app.features.documents import service as document_service
from app.features.documents.pages import FieldValue, PageReading, PageRecord
from app.features.documents.reader import Page, PasswordNeeded, UnreadableFile, file_kind, read_document
from app.features.documents.repository import DocumentRepository
from app.features.documents.service import DocumentService
from tests.documents.test_service import drop_test_mappings, fake_model, temp_uploads, user_id


__all__ = ["drop_test_mappings", "fake_model", "temp_uploads", "user_id"]

read: list[int] = []


def pdf_with(stream: str) -> bytes:

    """A one-page PDF drawing the given content stream in Helvetica."""

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 400] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
    body = "%PDF-1.4\n"
    offsets = []

    for number, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n{content}\nendobj\n"

    start = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    body += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    body += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n"

    return body.encode()


def text_pdf() -> bytes:

    """A PDF page of plain lines with no table, like a CAS statement."""

    lines = ["Consolidated Account Statement", "Parag Parikh Flexi Cap Fund Direct Growth", "Closing units 125.450 Value Rs 2,87,500.00"]
    stream = "BT /F1 12 Tf 40 340 Td " + " 0 -20 Td ".join(f"({line}) Tj" for line in lines) + " ET"

    return pdf_with(stream)


def table_pdf() -> bytes:

    """A PDF page with a ruled two-row table: Date, Narration, Withdrawal."""

    grid = "0.5 w 40 300 m 460 300 l S 40 270 m 460 270 l S 40 240 m 460 240 l S"
    grid += " 40 300 m 40 240 l S 160 300 m 160 240 l S 340 300 m 340 240 l S 460 300 m 460 240 l S"
    cells = [(45, 280, "Date"), (165, 280, "Narration"), (345, 280, "Withdrawal Amt."), (45, 250, "01/10/2026"), (165, 250, "UPI-TEST"), (345, 250, "450.00")]
    text = " ".join(f"BT /F1 10 Tf {x} {y} Td ({value}) Tj ET" for x, y, value in cells)

    return pdf_with(f"{grid} {text}")


def png() -> bytes:

    """A small white picture, standing in for a photo of a statement."""

    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buffer, format="PNG")

    return buffer.getvalue()


@pytest.fixture(autouse=True)
def fake_page_model(monkeypatch: pytest.MonkeyPatch) -> None:

    """Answer every page with one holding, copied as printed, and count the pages read."""

    read.clear()

    async def answer(page: Page) -> PageReading:

        """One fund line, with its value written the way a statement prints it."""

        read.append(page.number)

        return PageReading(rows=[PageRecord(target_table="holdings", fields=[
            FieldValue(name="security_name", value="Parag Parikh Flexi Cap Fund Direct Growth"),
            FieldValue(name="units", value="125.450"),
            FieldValue(name="current_value", value="Rs 2,87,500.00"),
            FieldValue(name="asset_type", value="mutual_fund"),
            ])])

    monkeypatch.setattr(page_module, "read_page", answer)


def test_text_page_and_table_page_are_told_apart() -> None:

    """A page with a ruled table becomes a sheet for code; a page of lines becomes text for the model."""

    tables = read_document(".pdf", table_pdf())
    lines = read_document(".pdf", text_pdf())

    assert len(tables.sheets) == 1 and not tables.pages
    assert tables.sheets[0].row_values(1) == ["01/10/2026", "UPI-TEST", "450.00"]
    assert not lines.sheets and lines.pages[0].text and "Closing units" in lines.pages[0].text


def test_only_accepted_files_pass() -> None:

    """Videos and renamed files are refused before anything is read."""

    with pytest.raises(UnreadableFile):
        file_kind("clip.mp4", b"\x00\x00\x00\x18ftypmp42")

    with pytest.raises(UnreadableFile):
        file_kind("statement.pdf", png())

    assert file_kind("photo.png", png()) == ".png"


async def test_pages_wait_for_your_ok_then_the_model_reads_them(user_id: int) -> None:

    """A PDF of plain lines waits for the user's OK; once given, the model's values are cleaned by code and marked to check."""

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "cas.pdf", text_pdf())

    assert document.status == DocumentStatus.needs_consent
    assert document.summary["pending_pages"] == {"count": 1, "pictures": 0}
    assert read == []

    async with SessionLocal() as session:
        document = await DocumentService(session).allow_model(user_id, document.id)
        rows = await DocumentRepository(session).rows(document.id)

    assert document.status == DocumentStatus.parsed
    assert read == [1]
    assert rows[0].parsed_data["current_value"] == "287500.00"
    assert rows[0].parsed_data["units"] == "125.4500"
    assert "asset_type" not in rows[0].parsed_data or rows[0].parsed_data["asset_type"] == "mutual_fund"
    assert rows[0].source["read_by_model"] is True
    assert rows[0].warnings and "Read by the model" in rows[0].warnings[0]


async def test_a_photo_waits_for_your_ok(user_id: int) -> None:

    """A photo is never sent to the model before the user says yes."""

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "photo.png", png())

    assert document.status == DocumentStatus.needs_consent
    assert document.summary["pending_pages"] == {"count": 1, "pictures": 1}
    assert read == []


async def test_a_pdf_table_needs_no_ok(user_id: int) -> None:

    """A PDF whose page is a table is read by code and the column plan, with no page sent to the model."""

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "bank.pdf", table_pdf())
        rows = await DocumentRepository(session).rows(document.id)

    assert document.status == DocumentStatus.parsed
    assert read == []
    assert rows[0].parsed_data["amount"] == "450.00"


async def test_locked_pdf_waits_for_its_password(
    user_id: int,
    monkeypatch: pytest.MonkeyPatch
    ) -> None:

    """A locked PDF waits for a password, a wrong one says so, and the right one reads the file."""

    def locked(
        ending: str,
        data: bytes,
        password: str | None = None
        ) -> object:

        """Open only with the password 'secret'."""

        if password != "secret":
            raise PasswordNeeded("This PDF is locked. Give its password to read it.")

        return read_document(ending, data)

    monkeypatch.setattr(document_service, "read_document", locked)

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "cas.pdf", table_pdf())

    assert document.status == DocumentStatus.needs_password

    async with SessionLocal() as session:
        document = await DocumentService(session).unlock(user_id, document.id, "wrong")

    assert document.status == DocumentStatus.needs_password
    assert "did not open" in document.error_message

    async with SessionLocal() as session:
        document = await DocumentService(session).unlock(user_id, document.id, "secret")

    assert document.status == DocumentStatus.parsed
    assert document.summary["locked"] is True
