"""The upload flow: check and save the file, pick its family or mapping, parse it into rows, and hold them for review."""

import asyncio
import hashlib
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.enums import DocumentStatus
from app.db.models import Document, ImportRow
from app.features.documents.families import TooManyFamilies, classify
from app.features.documents.layouts import (
    SheetLayout,
    as_proposal,
    columns_of,
    layout_of,
    mapping_errors,
    parse_mapped,
    propose_mapping,
    )
from app.features.documents.parsing import ParsedRow, ParseResult, SheetNote
from app.features.documents.reader import MIME_TYPES, Sheet, UnreadableFile, file_kind, read_file
from app.features.documents.repository import DocumentRepository
from app.features.documents.schemas import SheetChoice
from app.features.documents.storage import load_file, save_file


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

        if existing is not None and existing.status != DocumentStatus.failed:
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
        data: bytes
        ) -> None:

        """Parse the file from scratch and save the outcome, marking the document failed with a plain reason on any error."""

        try:
            sheets = await asyncio.to_thread(read_file, ending, data)
            family = classify(sheets)

            if family is not None:
                result = family.parse(sheets)
                document.family = family.name
                pending: list[dict[str, Any]] = []

            else:
                result, pending = await self.parse_unknown(sheets)
                document.family = MAPPED_FAMILY

            await self.save_result(document, result, pending)

        except (UnreadableFile, TooManyFamilies, MappingFailed) as exc:
            await self.fail(document, str(exc))

        except Exception:
            log.exception("document %s failed to parse", document.id)
            await self.fail(document, "The file could not be read. Nothing was imported.")

        await self.session.commit()

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
        pending: list[dict[str, Any]]
        ) -> None:

        """Store the parsed rows and sheet notes, or wait for the user when any sheet still needs a mapping."""

        notes = [note.as_dict() for note in result.notes]

        if pending:
            document.status = DocumentStatus.needs_mapping
            document.summary = {"sheets": notes, "pending_mappings": pending, "row_count": 0}
            document.error_message = None
            await self.repository.replace_rows(document.id, [])

            return

        rows = numbered_rows(document, result.rows)
        document.status = DocumentStatus.parsed if rows else DocumentStatus.failed
        document.summary = {"sheets": notes, "pending_mappings": [], "row_count": len(rows)}
        document.error_message = None if rows else NO_ROWS_MESSAGE
        await self.repository.replace_rows(document.id, rows)

    async def parse_unknown(self, sheets: list[Sheet]) -> tuple[ParseResult, list[dict[str, Any]]]:

        """Read each sheet with its confirmed mapping, asking the model for a proposal where none is confirmed yet."""

        result = ParseResult()
        pending = []
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

            if mapping is not None and mapping.confirmed_at is not None:
                result.notes.append(self.read_confirmed(layout, mapping.target_table, mapping.columns, result))
                continue

            if mapping is not None:
                pending.append(as_proposal(layout, mapping.target_table, mapping.columns, mapping.reason))

            else:
                pending.append(await self.ask_model(layout))

            result.notes.append(SheetNote(layout.sheet.name, "needs_mapping", "Waiting for you to confirm how its columns map"))

        return result, pending

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

        rows = parse_mapped(layout.sheet, layout.headers, target_table, columns)
        result.rows.extend(rows)

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

        """Save the user's mappings for every waiting sheet, then parse the file again with them."""

        document = await self.get(user_id, document_id)

        if document.status != DocumentStatus.needs_mapping:
            raise MappingNotExpected("This document is not waiting for a mapping")

        by_sheet = {choice.sheet: choice for choice in choices}
        pending = document.summary.get("pending_mappings", [])
        errors = []

        for proposal in pending:

            choice = by_sheet.get(proposal["sheet"])
            target_table = choice.target_table if choice else proposal["target_table"]
            columns = choice.columns if choice else proposal["columns"]

            for error in mapping_errors(target_table, columns, proposal["headers"]):
                errors.append(f"{proposal['sheet']}: {error}")

            proposal["confirmed"] = {"target_table": target_table, "columns": columns}

        if errors:
            raise MappingInvalid(errors)

        for proposal in pending:
            await self.repository.confirm(
                proposal["fingerprint"],
                proposal["headers"],
                proposal["confirmed"]["target_table"],
                proposal["confirmed"]["columns"],
                user_id,
                )

        data = await load_file(document.storage_path)
        await self.process(document, file_kind(document.original_filename, data), data)

        return document

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
            source=row.source,
            errors=row.errors,
            warnings=row.warnings,
            ))

    return rows
