"""Tests for naming attached uploads in a chat message, so the agent knows which files came with it."""

import pytest
from pydantic import ValidationError

from app.db.session import SessionLocal
from app.features.documents.service import DocumentNotFound, DocumentService
from app.features.runs.schemas import CreateRunRequest
from app.features.runs.service import RunService
from tests.documents.test_planner_workbook import build_workbook
from tests.documents.test_service import fake_model, temp_uploads, user_id


__all__ = ["fake_model", "temp_uploads", "user_id"]


def test_files_alone_are_enough_to_send() -> None:

    """A message may be empty when files are attached, but not when nothing is sent at all."""

    assert CreateRunRequest(client_request_id="a", document_ids=[3]).message == ""

    with pytest.raises(ValidationError):
        CreateRunRequest(client_request_id="b")


async def test_attached_files_are_named_with_their_ids(user_id: int) -> None:

    """Each attached upload is named with its id after the user's words, or with a plain request when there are none."""

    async with SessionLocal() as session:
        document, _ = await DocumentService(session).upload(user_id, "plan.xlsx", build_workbook())

    async with SessionLocal() as session:
        with_words = await RunService(session).with_attachments("Import this", [document.id, document.id], user_id)
        alone = await RunService(session).with_attachments("  ", [document.id], user_id)

    assert with_words == f"Import this\n\nAttached: plan.xlsx (document {document.id})."
    assert alone == f"Attached: plan.xlsx (document {document.id}). Please read it."


async def test_someone_elses_upload_is_refused(user_id: int) -> None:

    """An id that is not the user's upload is refused, so no one can point the agent at another person's file."""

    async with SessionLocal() as session:

        with pytest.raises(DocumentNotFound):
            await RunService(session).with_attachments("", [987654321], user_id)


@pytest.mark.parametrize("status", ["needs_password", "needs_consent", "needs_mapping", "parsed", "imported"])
def test_agent_messages_never_carry_links_or_ids(status: str) -> None:

    """Whatever state an upload is in, the words the agent is told to say hold no link and no document id."""

    from app.agent.tools.imports import preview_message

    data = {
        "document_id": 227,
        "file": "holdings.xlsx",
        "status": status,
        "counts": {"holdings": {"create": 3}},
        "saved": {"holdings": 78},
        "failed": 2,
        "open_question_count": 2,
        "error_count": 1,
        "pending_pages": {"count": 1, "pictures": 1},
        "read_by_model": 0,
        }

    message = preview_message(data)

    assert "/documents" not in message
    assert "227" not in message
    assert "holdings.xlsx" in message
