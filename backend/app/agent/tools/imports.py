"""The document import tools: read an upload's preview and questions, save the user's answer, approve the import, and undo it."""

from collections import Counter
from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import PlannerContext
from app.agent.tools.limits import tool_session
from app.agent.tools.operations import run_write
from app.agent.tools.results import ToolResult, checked, conflict, invalid, not_found, ok, to_message
from app.db.enums import ImportRowStatus
from app.db.models import Document, ImportRow
from app.features.documents.repository import DocumentRepository
from app.features.documents.schemas import AnswerIn
from app.features.documents.service import AnswerInvalid, DocumentNotFound, DocumentService, NothingToApprove, NothingToUndo
from app.features.documents.writer import UndoBlocked
from app.features.records.exceptions import RecordError


SHOWN_QUESTIONS = 5
SHOWN_ERRORS = 5


def review_link(document_id: int) -> str:

    """Where the review screen for one upload lives in the app."""

    return f"/documents/{document_id}"


def table_counts(rows: list[ImportRow]) -> dict[str, dict[str, int]]:

    """For each table, how many open rows would be created, updated or left unchanged."""

    counts: dict[str, Counter] = {}

    for row in rows:

        if row.status == ImportRowStatus.proposed and row.action is not None:
            counts.setdefault(row.target_table, Counter())[row.action.value] += 1

    return {table: dict(counter) for table, counter in counts.items()}


def counts_line(counts: dict[str, dict[str, int]]) -> list[str]:

    """Each table's counts as a short line, such as 'holdings: 72 new, 1 update'."""

    words = {"create": "new", "update": "update", "no_change": "no change"}

    return [f"{table}: {', '.join(f'{number} {words[action]}' for action, number in actions.items())}" for table, actions in counts.items()]


def open_questions(rows: list[ImportRow]) -> list[dict[str, Any]]:

    """Every unanswered question with its row, for the model to ask or to point at the review screen."""

    asked = []

    for row in rows:

        if row.status != ImportRowStatus.proposed:
            continue

        for item in row.questions:

            if item.get("answer") is None:
                asked.append({"row_id": row.id, "row_number": row.row_number, "question_id": item["id"], "text": item["text"], "options": item["options"]})

    return asked


async def find_document(
    session: AsyncSession,
    user_id: int,
    document_id: int | None
    ) -> Document | None:

    """The upload asked for, or the user's newest one when no id is given."""

    repository = DocumentRepository(session)

    if document_id is not None:
        return await repository.get(user_id, document_id)

    documents = await repository.list_for_user(user_id)

    return documents[0] if documents else None


def preview_data(
    document: Document,
    rows: list[ImportRow]
    ) -> dict[str, Any]:

    """What the model needs to explain an upload: counts, sheet notes, open questions and errors."""

    questions = open_questions(rows)
    errors = [
        {"row_number": row.row_number, "table": row.target_table, "error": row.errors[0]}
        for row in rows
        if row.status in (ImportRowStatus.proposed, ImportRowStatus.failed) and row.errors
        ]

    return {
        "document_id": document.id,
        "file": document.original_filename,
        "status": document.status.value,
        "counts": table_counts(rows),
        "checks": document.summary.get("checks", {}),
        "sheets": document.summary.get("sheets", []),
        "open_question_count": len(questions),
        "open_questions": questions[:SHOWN_QUESTIONS],
        "error_count": len(errors),
        "errors": errors[:SHOWN_ERRORS],
        "review_link": review_link(document.id),
        }


def preview_message(data: dict[str, Any]) -> str:

    """The next step for the model, by how many questions are open: ask one in chat, or send the user to the review screen."""

    lines = counts_line(data["counts"])
    summary = f"{data['file']} is {data['status']}. Ready to import: {'; '.join(lines) or 'nothing yet'}."
    count = data["open_question_count"]

    if count == 1:
        return f"{summary} One question is open. Ask it in chat in simple words with its choices, then save the reply with answer_import_question. Do not pick for the user."

    if count > 1:
        return f"{summary} {count} questions are open. Do not ask them in chat. Send the user to the review screen at {data['review_link']} to answer them one by one."

    if data["error_count"]:
        return f"{summary} {data['error_count']} rows have errors to fix on the review screen at {data['review_link']}. The ready rows can be approved now with approve_import."

    return f"{summary} Every row is ready. Ask the user if they want to import it, then call approve_import."


@tool
async def get_import_preview(
    runtime: ToolRuntime[PlannerContext],
    document_id: Annotated[int | None, "The upload's id. Leave out for the user's newest upload."] = None,
    ) -> ToolMessage:

    """Read what an uploaded file would import: counts per table, sheet notes, open questions and errors. Read-only. Use it when the user uploads a file or asks about an import."""

    async with tool_session(runtime.context) as session:

        document = await find_document(session, runtime.context.user_id, document_id)

        if document is None:
            return to_message(not_found("No uploaded file was found."), runtime.tool_call_id)

        data = preview_data(document, await DocumentRepository(session).rows(document.id))

    return to_message(ok(preview_message(data), data), runtime.tool_call_id)


@tool
async def answer_import_question(
    runtime: ToolRuntime[PlannerContext],
    document_id: Annotated[int, "The upload's id, from get_import_preview."],
    row_id: Annotated[int, "The row_id of the question, from get_import_preview."],
    question_id: Annotated[str, "The question_id, from get_import_preview."],
    answer: Annotated[str, "The value of the choice the user picked, exactly as listed in options."],
    ) -> ToolMessage:

    """Save the user's own answer to one open import question. Only use the choice the user said in chat, never your own guess."""

    async def save(session: AsyncSession) -> ToolResult:

        """Save the answer and report what is still open."""

        try:
            document = await DocumentService(session).answer(runtime.context.user_id, document_id, [AnswerIn(row_id=row_id, question_id=question_id, answer=answer)])

        except DocumentNotFound:
            return not_found("That upload was not found.")

        except AnswerInvalid as exc:
            return invalid("bad_answer", str(exc))

        rows = await DocumentRepository(session).rows(document.id)
        data = preview_data(document, rows)

        return checked(f"Answer saved. {preview_message(data)}", data)

    return to_message(await run_write(runtime, save), runtime.tool_call_id)


@tool
async def approve_import(
    runtime: ToolRuntime[PlannerContext],
    document_id: Annotated[int, "The upload's id, from get_import_preview."],
    ) -> ToolMessage:

    """Import every ready row of an upload into the user's saved records. The user approves on a card first. Rows with errors or open questions wait."""

    async def write(session: AsyncSession) -> ToolResult:

        """Write the ready rows and report how many were written, unchanged or failed."""

        try:
            outcome = await DocumentService(session).approve(runtime.context.user_id, document_id)

        except DocumentNotFound:
            return not_found("That upload was not found.")

        except NothingToApprove as exc:
            return invalid("nothing_ready", str(exc))

        message = f"Imported {outcome['written']} rows, {outcome['no_change']} had no change."

        if outcome["failed"]:
            message += f" {outcome['failed']} could not be saved; their reasons are on the review screen at {review_link(document_id)}."

        return checked(message, {**outcome, "review_link": review_link(document_id)})

    return to_message(await run_write(runtime, write), runtime.tool_call_id)


@tool
async def undo_import(
    runtime: ToolRuntime[PlannerContext],
    document_id: Annotated[int, "The upload's id, from get_import_preview."],
    ) -> ToolMessage:

    """Undo everything an upload imported: remove the records it added and put back the values it changed. The user approves on a card first. Refused when a record was changed after the import."""

    async def remove(session: AsyncSession) -> ToolResult:

        """Undo the import and report how many rows were undone."""

        try:
            count = await DocumentService(session).undo(runtime.context.user_id, document_id)

        except DocumentNotFound:
            return not_found("That upload was not found.")

        except NothingToUndo as exc:
            return invalid("nothing_to_undo", str(exc))

        except UndoBlocked as exc:
            return conflict("changed_after_import", f"Nothing was undone. {'; '.join(exc.reasons)}.")

        except RecordError as exc:
            return conflict("linked", f"Nothing was undone. {exc}")

        return checked(f"Undid {count} imported rows.", {"undone": count})

    return to_message(await run_write(runtime, remove), runtime.tool_call_id)

