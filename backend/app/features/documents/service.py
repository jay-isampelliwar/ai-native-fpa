"""The upload flow: check and save the file, pick its family or mapping, parse it into rows, and hold them for review."""

import asyncio
import hashlib
import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.enums import DocumentStatus, ImportRowAction, ImportRowStatus
from app.db.models import Document, ImportRow
from app.features.documents.checks import counts, ready, run_checks
from app.features.documents.fields import TABLE_FIELDS, dated_tables, read_value
from app.features.documents.families import TooManyFamilies, classify
from app.features.documents.layouts import (
    SheetLayout,
    as_proposal,
    columns_of,
    layout_of,
    mapping_errors,
    parse_mapped,
    propose_mapping,
    usable_columns,
    )
from app.features.documents.parsing import ParsedRow, ParseResult, SheetNote
from app.features.documents.pages import page_summary, read_pages
from app.features.documents.reader import MIME_TYPES, Page, PasswordNeeded, Sheet, UnreadableFile, file_kind, read_document
from app.features.documents.repository import DocumentRepository
from app.features.documents.matching import instrument_by_answer
from app.features.documents.normalize import NotReadable
from app.features.documents.schemas import AnswerIn, RowEdit, SheetChoice
from app.features.documents.storage import load_file, save_file
from app.features.documents.writer import WRITE_ERRORS, Writer, write_reason


log = logging.getLogger(__name__)

MAPPED_FAMILY = "mapped"

NO_ROWS_MESSAGE = "No records were found in this file. See each sheet's note for why."


class DocumentTooLarge(ValueError):

    """A file over the upload size limit."""


class DocumentNotFound(LookupError):

    """A document that does not exist or is not the user's."""


class MappingNotExpected(ValueError):

    """A mapping sent for a document that is not waiting for one."""


class MappingInvalid(ValueError):

    """A mapping that fails the checks, with every reason listed."""

    def __init__(self, errors: list[str]) -> None:

        """Keep every reason the mapping was refused."""

        super().__init__("; ".join(errors))
        self.errors = errors


class AnswerInvalid(ValueError):

    """Answers that do not fit the questions asked, with every reason listed."""

    def __init__(self, errors: list[str]) -> None:

        """Keep every reason the answers were refused."""

        super().__init__("; ".join(errors))
        self.errors = errors


class EditInvalid(ValueError):

    """Row changes that cannot be read, with every reason listed."""

    def __init__(self, errors: list[str]) -> None:

        """Keep every reason the changes were refused."""

        super().__init__("; ".join(errors))
        self.errors = errors


class NothingToApprove(ValueError):

    """An approval with no ready rows, or on a document not waiting for one."""


class NothingToUndo(ValueError):

    """An undo on a document that wrote nothing."""


class MappingFailed(RuntimeError):

    """The model could not be asked for a mapping."""


class DocumentService:

    """Runs uploads and mapping confirmations for one request, committing as it goes."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the session and a repository on it."""

        self.session = session
        self.repository = DocumentRepository(session)

    async def upload(
        self,
        user_id: int,
        filename: str,
        data: bytes
        ) -> tuple[Document, bool]:

        """Check, save and parse one file, returning the document and whether it was an earlier upload of the same file."""

        if len(data) > get_settings().MAX_DOCUMENT_BYTES:
            raise DocumentTooLarge("The file is larger than the upload limit")

        ending = file_kind(filename, data)
        sha256 = hashlib.sha256(data).hexdigest()
        existing = await self.repository.find_by_hash(user_id, sha256)

        if existing is not None and existing.status not in (DocumentStatus.failed, DocumentStatus.needs_mapping):
            return existing, True

        if existing is not None:
            await self.process(existing, ending, data)

            return existing, True

        document = Document(
            user_id=user_id,
            original_filename=filename[:255],
            mime_type=MIME_TYPES[ending],
            file_size_bytes=len(data),
            sha256=sha256,
            storage_path=await save_file(user_id, ending, data),
            status=DocumentStatus.uploaded,
            )

        self.repository.add(document)
        await self.session.commit()
        await self.process(document, ending, data)

        return document, False

    async def process(
        self,
        document: Document,
        ending: str,
        data: bytes,
        password: str | None = None
        ) -> None:

        """Read the file from scratch and save the outcome, waiting for a password or the user's OK where needed, and failing with a plain reason on any error."""

        try:
            content = await asyncio.to_thread(read_document, ending, data, password)
            family = classify(content.sheets) if content.sheets else None
            plans: list[dict[str, Any]] = []
            pending: list[dict[str, Any]] = []

            if family is not None:
                result = family.parse(content.sheets)
                document.family = family.name

            else:
                result, pending, plans = await self.parse_unknown(content.sheets)
                document.family = MAPPED_FAMILY

            if content.pages and not document.summary.get("model_allowed"):
                await self.wait(document, DocumentStatus.needs_consent, None, {"pending_pages": page_summary(content.pages)})

            else:

                if content.pages:
                    page_rows, page_notes, page_totals = await self.read_with_model(content.pages)
                    result.rows.extend(page_rows)
                    result.notes.extend(page_notes)
                    result.printed.extend(page_totals)

                await self.save_result(document, result, pending, plans)

        except PasswordNeeded as exc:
            message = "That password did not open the PDF. Try again." if password else str(exc)
            await self.wait(document, DocumentStatus.needs_password, message, {"locked": True})

        except (UnreadableFile, TooManyFamilies, MappingFailed) as exc:
            await self.fail(document, str(exc))

        except Exception:
            log.exception("document %s failed to parse", document.id)
            await self.fail(document, "The file could not be read. Nothing was imported.")

        await self.session.commit()

    async def read_with_model(self, pages: list[Page]) -> tuple[list[ParsedRow], list[SheetNote], list[dict[str, Any]]]:

        """Have the model read the pages, turning any failure into a plain reason."""

        try:
            return await read_pages(pages)

        except Exception as exc:
            log.exception("page model failed")
            raise MappingFailed("The model could not read the pages of this file. Try again later.") from exc

    async def wait(
        self,
        document: Document,
        status: DocumentStatus,
        message: str | None,
        extra: dict[str, Any]
        ) -> None:

        """Hold the document for the user, such as for a password or an OK to let the model read it, with no rows yet."""

        document.status = status
        document.error_message = message
        document.summary = {**kept_summary(document), "sheets": [], "pending_mappings": [], "plans": [], "row_count": 0, **extra}
        await self.repository.replace_rows(document.id, [])

    async def fail(
        self,
        document: Document,
        message: str
        ) -> None:

        """Mark the document failed and clear any rows from an earlier attempt."""

        await self.session.rollback()
        await self.session.refresh(document)
        document.status = DocumentStatus.failed
        document.error_message = message
        self.session.add(document)
        await self.repository.replace_rows(document.id, [])

    async def save_result(
        self,
        document: Document,
        result: ParseResult,
        pending: list[dict[str, Any]],
        plans: list[dict[str, Any]] | None = None
        ) -> None:

        """Store the parsed rows, sheet notes and the column plans used, or wait for the user when a sheet's plan failed its checks."""

        notes = [note.as_dict() for note in result.notes]
        base = {**kept_summary(document), "sheets": notes, "plans": plans or [], "printed_totals": result.printed}

        if pending:
            document.status = DocumentStatus.needs_mapping
            document.summary = {**base, "pending_mappings": pending, "row_count": 0}
            document.error_message = None
            await self.repository.replace_rows(document.id, [])

            return

        rows = numbered_rows(document, result.rows)
        document.status = DocumentStatus.parsed if rows else DocumentStatus.failed
        document.summary = {**base, "pending_mappings": [], "row_count": len(rows)}
        document.error_message = None if rows else NO_ROWS_MESSAGE
        await self.repository.replace_rows(document.id, rows)

        if rows:
            await self.session.flush()
            await run_checks(self.session, document)

    async def parse_unknown(self, sheets: list[Sheet]) -> tuple[ParseResult, list[dict[str, Any]], list[dict[str, Any]]]:

        """Read each sheet with its saved or proposed column plan when the plan passes the checks, and hold back only the sheets whose plan does not."""

        result = ParseResult()
        pending = []
        plans = []
        layouts: list[SheetLayout] = []

        for sheet in sheets:

            if sheet.hidden:
                result.notes.append(SheetNote(sheet.name, "not_imported", "Hidden sheet, not imported"))
                continue

            layout = layout_of(sheet)

            if layout is None:
                outcome = "not_imported" if any(any(row) for row in sheet.rows) else "empty"
                result.notes.append(SheetNote(sheet.name, outcome, "No header row found, not imported"))
                continue

            layouts.append(layout)

        saved = await self.repository.mappings([layout.fingerprint for layout in layouts])

        for layout in layouts:

            mapping = saved.get(layout.fingerprint)

            if mapping is None:
                plan = await self.ask_model(layout)

            else:
                plan = as_proposal(layout, mapping.target_table, usable_columns(mapping.target_table, mapping.columns), mapping.reason)
                plan["confirmed_at"] = mapping.confirmed_at.isoformat() if mapping.confirmed_at else None

            if plan["errors"]:
                pending.append(plan)
                result.notes.append(SheetNote(layout.sheet.name, "needs_mapping", "Its column plan failed the checks. Pick the columns to read it."))
                continue

            plans.append(plan)
            result.notes.append(self.read_confirmed(layout, plan["target_table"], plan["columns"], result))

        return result, pending, plans

    def read_confirmed(
        self,
        layout: SheetLayout,
        target_table: str | None,
        columns: dict[str, Any],
        result: ParseResult
        ) -> SheetNote:

        """Read one sheet with a confirmed mapping and describe what came of it."""

        if target_table is None:
            return SheetNote(layout.sheet.name, "not_imported", "Sheet not imported: its saved mapping says it holds no records")

        mapped = parse_mapped(layout.sheet, layout.headers, target_table, columns)
        rows = mapped.rows
        result.rows.extend(rows)
        result.printed.extend(mapped.printed)

        if not rows:
            return SheetNote(layout.sheet.name, "empty", "Sheet found, but no rows")

        return SheetNote(layout.sheet.name, "imported", f"{len(rows)} rows read into {target_table}", len(rows))

    async def ask_model(self, layout: SheetLayout) -> dict[str, Any]:

        """Ask the model for one sheet's mapping, save it as a proposal, and return it with its check results."""

        try:
            mapping = await propose_mapping(layout)

        except Exception as exc:
            log.exception("mapping model failed for sheet %s", layout.sheet.name)
            raise MappingFailed("This file's format is not known, and the model could not be asked to map it. Try again later.") from exc

        columns = columns_of(mapping)
        await self.repository.save_proposal(layout.fingerprint, layout.headers, mapping.target_table, columns, mapping.reason)

        return as_proposal(layout, mapping.target_table, columns, mapping.reason)

    async def confirm_mapping(
        self,
        user_id: int,
        document_id: int,
        choices: list[SheetChoice]
        ) -> Document:

        """Save the user's column plans, for sheets waiting for one or to change a plan already used, then read the file again."""

        document = await self.get(user_id, document_id)
        rows = await self.repository.rows(document.id)

        if document.status not in (DocumentStatus.needs_mapping, DocumentStatus.parsed) or any(row.status == ImportRowStatus.written for row in rows):
            raise MappingNotExpected("The columns of this file can no longer be changed")

        by_sheet = {choice.sheet: choice for choice in choices}
        sheets = [*document.summary.get("pending_mappings", []), *document.summary.get("plans", [])]
        chosen = []
        errors = []

        for plan in sheets:

            choice = by_sheet.get(plan["sheet"])
            target_table = choice.target_table if choice else plan["target_table"]
            columns = choice.columns if choice else plan["columns"]

            for error in mapping_errors(target_table, columns, plan["headers"]):
                errors.append(f"{plan['sheet']}: {error}")

            chosen.append((plan, target_table, columns))

        if errors:
            raise MappingInvalid(errors)

        for plan, target_table, columns in chosen:
            await self.repository.confirm(plan["fingerprint"], plan["headers"], target_table, columns, user_id)

        data = await load_file(document.storage_path)
        await self.process(document, file_kind(document.original_filename, data), data)

        return document

    async def unlock(
        self,
        user_id: int,
        document_id: int,
        password: str
        ) -> Document:

        """Read a locked PDF again with the password the user gave; the password is used for this read only and never saved."""

        document = await self.get(user_id, document_id)

        if document.status != DocumentStatus.needs_password:
            raise MappingNotExpected("This file is not waiting for a password")

        data = await load_file(document.storage_path)
        await self.process(document, file_kind(document.original_filename, data), data, password)

        return document

    async def allow_model(
        self,
        user_id: int,
        document_id: int,
        password: str | None = None
        ) -> Document:

        """Record the user's OK to let the model read this file's pages, then read it."""

        document = await self.get(user_id, document_id)

        if document.status != DocumentStatus.needs_consent:
            raise MappingNotExpected("This file is not waiting for your OK")

        document.summary = {**document.summary, "model_allowed": True}
        data = await load_file(document.storage_path)
        await self.process(document, file_kind(document.original_filename, data), data, password)

        return document

    async def answer(
        self,
        user_id: int,
        document_id: int,
        answers: list[AnswerIn]
        ) -> Document:

        """Save the user's answers to row questions, then check the whole document again, since one answer can settle others."""

        document = await self.get(user_id, document_id)

        if document.status != DocumentStatus.parsed:
            raise AnswerInvalid(["This document has no questions waiting"])

        rows = {row.id: row for row in await self.repository.rows(document.id)}
        errors = []

        for given in answers:

            row = rows.get(given.row_id)
            asked = next((item for item in (row.questions if row else []) if item["id"] == given.question_id), None)

            if asked is None:
                errors.append(f"Row {given.row_id} has no question {given.question_id}")
                continue

            if given.answer not in {choice["value"] for choice in asked["options"]}:
                errors.append(f"'{given.answer}' is not one of the choices for {given.question_id}")
                continue

            row.questions = [
                {**item, "answer": given.answer} if item["id"] == given.question_id else item
                for item in row.questions
                ]

        if errors:
            await self.session.rollback()
            raise AnswerInvalid(errors)

        await run_checks(self.session, document)
        await self.session.commit()

        return document

    async def edit(
        self,
        user_id: int,
        document_id: int,
        row_id: int,
        edit: RowEdit
        ) -> Document:

        """Save the user's changes to one row, each value cleaned and checked, then check the whole document again."""

        document = await self.get(user_id, document_id)
        row = next((item for item in await self.repository.rows(document.id) if item.id == row_id), None)

        if row is None:
            raise DocumentNotFound("Row not found")

        if row.status not in (ImportRowStatus.proposed, ImportRowStatus.failed):
            raise EditInvalid([f"Row {row.row_number} is {row.status.value} and cannot be changed"])

        fields = TABLE_FIELDS[row.target_table]
        cleaned: dict[str, Any] = {}
        errors = []

        for name, value in edit.changes.items():

            if name not in fields:
                errors.append(f"{name}: not a field of {row.target_table}")
                continue

            try:
                cleaned[name] = None if value in (None, "") else read_value(fields[name], value)

            except NotReadable as exc:
                errors.append(f"{name}: '{value}' {exc}")

        if edit.instrument is not None:

            if row.target_table != "holdings":
                errors.append("instrument: only holding rows have a stock or fund")

            elif await instrument_by_answer(self.session, edit.instrument) is None:
                errors.append(f"instrument: '{edit.instrument}' is not a stock or fund in the list")

            else:
                cleaned["instrument"] = edit.instrument

        if errors:
            raise EditInvalid(errors)

        row.edited_data = {**(row.edited_data or {}), **cleaned}
        row.status = ImportRowStatus.proposed
        await run_checks(self.session, document)
        await self.session.commit()

        return document

    async def remove_row(
        self,
        user_id: int,
        document_id: int,
        row_id: int,
        removed: bool
        ) -> Document:

        """Take one row out of this import, or bring it back; saved records are never touched, since a saved row is reversed with undo."""

        document = await self.get(user_id, document_id)
        row = next((item for item in await self.repository.rows(document.id) if item.id == row_id), None)

        if row is None:
            raise DocumentNotFound("Row not found")

        is_removed = bool((row.resolved or {}).get("removed"))
        open_statuses = (ImportRowStatus.proposed, ImportRowStatus.failed, ImportRowStatus.rejected)

        if row.status not in open_statuses or (not removed and not is_removed):
            raise EditInvalid([f"Row {row.row_number} is {row.status.value} and cannot be {'removed' if removed else 'brought back'}"])

        if removed:
            row.status = ImportRowStatus.rejected
            row.action = None
            row.resolved = {**(row.resolved or {}), "removed": True}

        else:
            row.status = ImportRowStatus.proposed
            row.resolved = {**(row.resolved or {}), "removed": False, "skipped": False}

        rows = await self.repository.rows(document.id)
        waiting = any(item.status in (ImportRowStatus.proposed, ImportRowStatus.failed) for item in rows)
        written = any(item.status == ImportRowStatus.written for item in rows)

        if document.status in (DocumentStatus.parsed, DocumentStatus.imported):
            document.status = DocumentStatus.parsed if waiting or not written else DocumentStatus.imported

        await run_checks(self.session, document)
        await self.session.commit()

        return document

    async def accept_totals(
        self,
        user_id: int,
        document_id: int
        ) -> Document:

        """Record that the user saw the totals mismatch and chose to import anyway; it holds only while the mismatch stays the same."""

        document = await self.get(user_id, document_id)
        await run_checks(self.session, document)
        key = document.summary.get("totals_key")

        if key is None:
            raise EditInvalid(["The totals already match"])

        document.summary = {**document.summary, "totals_accepted_for": key, "totals_blocked": False}
        await self.session.commit()

        return document

    async def set_as_of_date(
        self,
        user_id: int,
        document_id: int,
        as_of: date
        ) -> Document:

        """Give every open row that needs an as-of date and has none the date the user chose, then check the document again."""

        if as_of > date.today():
            raise EditInvalid(["as_of_date: cannot be in the future"])

        document = await self.get(user_id, document_id)
        dated = dated_tables()
        changed = 0

        for row in await self.repository.rows(document.id):

            data = {**row.parsed_data, **(row.edited_data or {})}

            if row.status in (ImportRowStatus.proposed, ImportRowStatus.failed) and row.target_table in dated and not data.get("as_of_date"):
                row.edited_data = {**(row.edited_data or {}), "as_of_date": as_of.isoformat()}
                row.status = ImportRowStatus.proposed
                changed += 1

        if not changed:
            raise EditInvalid(["No rows are missing an as-of date"])

        await run_checks(self.session, document)
        await self.session.commit()

        return document

    async def approve(
        self,
        user_id: int,
        document_id: int
        ) -> dict[str, int]:

        """Write every ready row, each on its own so one failure keeps the rest, and say how many were written."""

        document = await self.get(user_id, document_id)

        if document.status != DocumentStatus.parsed:
            raise NothingToApprove("This document has nothing waiting to be approved")

        await run_checks(self.session, document)
        rows = await self.repository.rows(document.id)
        by_number = {row.row_number: row for row in rows}
        waiting = [row for row in rows if ready(row)]

        if not waiting:
            raise NothingToApprove("No rows are ready yet. Answer the open questions and fix the errors first.")

        if document.summary.get("totals_blocked"):
            raise NothingToApprove("The rows do not add up to the totals in the file. Look at the totals in the review, then fix the rows or pick Import anyway.")

        for plan in document.summary.get("plans", []):

            if not plan.get("confirmed_at"):
                await self.repository.confirm(plan["fingerprint"], plan["headers"], plan["target_table"], plan["columns"], user_id)

        writer = Writer(self.session, user_id)
        outcome = {"written": 0, "no_change": 0, "failed": 0}

        for row in waiting:

            if row.action == ImportRowAction.no_change:
                row.status = ImportRowStatus.written
                row.written_at = datetime.now(UTC)
                outcome["no_change"] += 1
                continue

            data = {**row.parsed_data, **(row.edited_data or {}), **{key: row.resolved[key] for key in ("current_value",) if key in row.resolved}}

            try:

                async with self.session.begin_nested():
                    written = await writer.write(row, data, by_number)

            except WRITE_ERRORS as exc:
                row.status = ImportRowStatus.failed
                row.errors = [write_reason(exc)]
                outcome["failed"] += 1
                continue

            row.target_record_id = written.record_id
            row.previous_data = written.previous
            row.resolved = {**row.resolved, "written": written.written}
            row.status = ImportRowStatus.written
            row.written_at = datetime.now(UTC)
            outcome["written"] += 1

        open_rows = [row for row in rows if row.status in (ImportRowStatus.proposed, ImportRowStatus.failed)]
        document.status = DocumentStatus.parsed if open_rows else DocumentStatus.imported
        document.summary = {**document.summary, "last_approval": outcome, "checks": counts(rows)}
        await self.session.commit()

        return outcome

    async def undo(
        self,
        user_id: int,
        document_id: int
        ) -> int:

        """Undo everything this document wrote in one go, or nothing when any record was changed after the import."""

        document = await self.get(user_id, document_id)
        rows = await self.repository.rows(document.id)
        written = [row for row in rows if row.status == ImportRowStatus.written and row.action != ImportRowAction.no_change]

        if not written:
            raise NothingToUndo("This document has nothing written to undo")

        try:
            await Writer(self.session, user_id).undo(written)

        except Exception:
            await self.session.rollback()
            raise

        for row in rows:

            if row.status == ImportRowStatus.written:
                row.status = ImportRowStatus.undone

        document.status = DocumentStatus.rejected
        document.summary = {**document.summary, "undone": len(written)}
        await self.session.commit()

        return len(written)

    async def get(
        self,
        user_id: int,
        document_id: int
        ) -> Document:

        """One of the user's documents, or DocumentNotFound."""

        document = await self.repository.get(user_id, document_id)

        if document is None:
            raise DocumentNotFound("Document not found")

        return document


KEPT_SUMMARY_KEYS = ("model_allowed", "locked", "totals_accepted_for")


def kept_summary(document: Document) -> dict[str, Any]:

    """The summary keys that outlive reading the file again, such as the user's OK for the model."""

    return {key: document.summary[key] for key in KEPT_SUMMARY_KEYS if key in (document.summary or {})}


def numbered_rows(
    document: Document,
    parsed: list[ParsedRow]
    ) -> list[ImportRow]:

    """Turn parsed rows into import rows numbered in file order, pointing each SIP at its holding's number."""

    numbers = {id(row): position + 1 for position, row in enumerate(parsed)}
    rows = []

    for position, row in enumerate(parsed):

        data = dict(row.data)

        if row.parent is not None:
            data["holding_row_number"] = numbers[id(row.parent)]

        rows.append(ImportRow(
            user_id=document.user_id,
            document_id=document.id,
            row_number=position + 1,
            target_table=row.target_table,
            parsed_data=data,
            source={**row.source, "read_errors": list(row.errors)},
            errors=row.errors,
            warnings=row.warnings,
            ))

    return rows
