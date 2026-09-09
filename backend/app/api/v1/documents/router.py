"""Upload, reconcile and commit endpoints, the volume path for getting real data in.

Upload returns before extraction finishes. A statement takes longer to read than a request should
stay open, so the handler stores the bytes, registers the import, starts a background job and
returns 202 with an id the client polls. That is why there is no synchronous variant: offering one
would mean the timeout behaviour differs by endpoint for the same work.

Nothing here writes a record. Extraction stages rows, a person accepts or corrects them, and only
``/commit`` writes - in one transaction, under one batch id. The separation is the same one that
governs the conversation: the system proposes, the human decides.

Re uploading a file already imported returns the existing import rather than creating a second one.
People forget which statements they have sent, and silently importing a month twice doubles every
figure that month feeds.

Size is checked before the body is read into memory. A large upload should be refused at the door,
not after the process has already allocated it.

Ownership failures are 404 throughout, matching every other surface: an import the caller does not
own is reported exactly as one that does not exist. An id nobody registered is refused the same way
and at the same moment - before the bytes are stored - because the alternative is what used to
happen: the upload succeeded, extraction succeeded, a person reviewed a dozen rows, and the foreign
key stopped it at the one call that writes.

The two mapping endpoints exist so an unfamiliar layout costs one confirmation rather than one every
month. ``/mapping/propose`` asks a model to read the column headings - never the data - and validates
what comes back; ``/mapping/confirm`` stores the person's decision as a template and re extracts. From
then on that layout parses deterministically with no model involved at all.

Mapping is available on any import whose layout was kept, not only on one that stopped for it. A
workbook nothing recognises is now read anyway - see ``app.extraction.sheets`` - so the common case
reaches ``extracted`` with rows to review and never sees this pair of endpoints. Someone who thinks
a column was read wrongly can still open the form, and the same confirmation still saves a template
and re extracts. Gating these on ``needs_mapping`` would have made correcting a reading impossible.

``/mapping/propose`` returns every candidate sheet and its columns whether or not the model answered.
The sheets used to be built from the proposal, so a failed or empty suggestion returned nothing to
map and the person was left with a card offering no columns and no way past it - which is what a
broken response schema turned into a dead end for every unrecognised layout. The columns come from
the file and the mapping is a suggestion laid over them, so the worst a model outage costs is that
the dropdowns start empty.
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select

from app.api.v1.documents.schemas import (
    BulkDecision,
    CommitResponse,
    ImportRead,
    MappingConfirmation,
    MappingProposal,
    MappingSheet,
    RowDecision,
    StagedRowRead,
    StagedRowsPage,
    StagedRowUpdate,
)
from app.core.config import settings
from app.db.session import session_scope
from app.models.orm.imports import DocumentImportRow, StagedRowRow
from app.models.orm.system import UserRow
from app.services.import_service import import_service
from app.storage.files import document_storage

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=ImportRead, status_code=202)
async def upload_document(user_id: int = Form(...), file: UploadFile = File(...)) -> ImportRead:

    """Store an upload, register it and start extraction in the background, returning immediately."""

    await known_user(user_id)

    content = await file.read()

    if len(content) > settings.maximum_upload_bytes:
        raise HTTPException(status_code=413, detail="that file is larger than the upload limit")

    if not content:
        raise HTTPException(status_code=400, detail="that file is empty")

    record, already_imported = await import_service.create_import(
        user_id=user_id,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        content=content,
        storage=document_storage,
    )

    if not already_imported:
        import_service.start_extraction(
            record.id,
            file.filename or "upload",
            file.content_type or "application/octet-stream",
            content,
        )

    return to_import_read(record, duplicate=already_imported)


async def known_user(user_id: int) -> None:

    """Refuse an id nobody registered, at the door rather than at the commit the constraint would stop."""

    async with session_scope() as session:

        if await session.get(UserRow, user_id) is None:
            raise HTTPException(status_code=404, detail="no such user")


@router.get("/{import_id}", response_model=ImportRead)
async def read_import(import_id: str, user_id: int) -> ImportRead:

    """Report where one import has reached, which is what a client polls after uploading."""

    record = await load_import(import_id, user_id)

    return to_import_read(record)


@router.get("/{import_id}/rows", response_model=StagedRowsPage)
async def list_staged_rows(import_id: str, user_id: int, limit: int = 200) -> StagedRowsPage:

    """List what was extracted, least confident first, so attention goes where it is worth spending."""

    record = await load_import(import_id, user_id)

    async with session_scope() as session:

        rows = (
            await session.scalars(
                select(StagedRowRow)
                .where(StagedRowRow.import_id == import_id)
                .order_by(StagedRowRow.confidence, StagedRowRow.row_index)
                .limit(limit)
            )
        ).all()

        counts = dict(
            (
                await session.execute(
                    select(StagedRowRow.status, func.count())
                    .where(StagedRowRow.import_id == import_id)
                    .group_by(StagedRowRow.status)
                )
            ).all()
        )

    return StagedRowsPage(
        import_id=import_id,
        status=record.status,
        total=sum(counts.values()),
        pending=counts.get("pending", 0),
        accepted=counts.get("accepted", 0),
        rejected=counts.get("rejected", 0),
        duplicates=counts.get("duplicate", 0),
        rows=[StagedRowRead.model_validate(row, from_attributes=True) for row in rows],
    )


@router.patch("/{import_id}/rows/{row_id}", response_model=StagedRowRead)
async def correct_staged_row(import_id: str, row_id: str, user_id: int, request: StagedRowUpdate) -> StagedRowRead:

    """Apply a person's correction to one row, which clears its issue and its doubt."""

    changes = request.model_dump(exclude_unset=True, mode="json")

    row = await import_service.update_row(user_id, row_id, changes)

    if row is None:
        raise HTTPException(status_code=404, detail="no such row")

    return StagedRowRead.model_validate(row, from_attributes=True)


@router.post("/{import_id}/rows/{row_id}/decision", response_model=StagedRowRead)
async def decide_staged_row(import_id: str, row_id: str, user_id: int, request: RowDecision) -> StagedRowRead:

    """Accept or reject one row, recording the decision the commit will act on."""

    row = await import_service.set_row_status(user_id, row_id, request.status)

    if row is None:
        raise HTTPException(status_code=404, detail="no such row")

    return StagedRowRead.model_validate(row, from_attributes=True)


@router.post("/{import_id}/decision", response_model=StagedRowsPage)
async def decide_all_rows(import_id: str, user_id: int, request: BulkDecision) -> StagedRowsPage:

    """Accept or reject every row at once, leaving duplicates alone unless asked otherwise."""

    await load_import(import_id, user_id)

    async with session_scope() as session:

        statement = select(StagedRowRow).where(StagedRowRow.import_id == import_id)

        if request.only_pending:
            statement = statement.where(StagedRowRow.status == "pending")

        for row in (await session.scalars(statement)).all():
            row.status = request.status

    return await list_staged_rows(import_id, user_id)


@router.post("/{import_id}/commit", response_model=CommitResponse)
async def commit_import(import_id: str, user_id: int) -> CommitResponse:

    """Write every accepted row under one batch id, in one transaction, or write none of them."""

    outcome = await import_service.commit(user_id, import_id)

    if outcome["status"] == "not_found":
        raise HTTPException(status_code=404, detail="no such import")

    return CommitResponse(**outcome)


async def load_import(import_id: str, user_id: int) -> DocumentImportRow:

    """Fetch an import this user owns, reporting one they do not own exactly as a missing one."""

    async with session_scope() as session:

        record = await session.scalar(
            select(DocumentImportRow).where(
                DocumentImportRow.id == import_id,
                DocumentImportRow.user_id == user_id,
            )
        )

    if record is None:
        raise HTTPException(status_code=404, detail="no such import")

    return record


def to_import_read(record: DocumentImportRow, duplicate: bool = False) -> ImportRead:

    """Narrow an import row into the client view, adding whether this upload was already seen."""

    return ImportRead(
        id=record.id,
        filename=record.filename,
        status=record.status,
        document_kind=record.document_kind,
        detected_format=record.detected_format,
        extractor=record.extractor,
        template_id=record.template_id,
        statement_totals=record.statement_totals,
        computed_totals=record.computed_totals,
        reconciled=record.reconciled,
        reconciliation_note=record.reconciliation_note,
        row_count=record.row_count,
        error=record.error,
        import_batch_id=record.import_batch_id,
        created_at=record.created_at,
        extracted_at=record.extracted_at,
        committed_at=record.committed_at,
        duplicate_of_existing_upload=duplicate,
        can_remap=bool(record.proposed_mapping),
    )


@router.post("/{import_id}/mapping/propose", response_model=MappingProposal)
async def propose_column_mapping(import_id: str, user_id: int) -> MappingProposal:

    """Suggest a column mapping for a layout nobody has confirmed, from headings and masked samples only."""

    record = await load_import(import_id, user_id)

    if not record.proposed_mapping:
        raise HTTPException(status_code=409, detail="this import has no layout to map")

    from app.extraction.mapping import describe_workbook, propose_mapping
    from app.extraction.workbook import WorkbookProfile

    profile = WorkbookProfile.model_validate(record.proposed_mapping["layout"])

    described = {sheet["sheet"]: sheet for sheet in describe_workbook(profile)}

    try:
        proposal, problems = await propose_mapping(profile)

    except Exception:
        proposal, problems = None, ["a mapping could not be suggested, so no column is filled in yet"]

    suggested = {sheet.sheet: sheet for sheet in proposal.sheets} if proposal else {}

    sheets = [
        MappingSheet(
            sheet=name,
            header_row=suggested[name].header_row if name in suggested else sheet["header_row"],
            asset_type=suggested[name].asset_type if name in suggested else "unknown",
            columns=sheet["columns"],
            mapping=suggested[name].mapping if name in suggested else {},
        )
        for name, sheet in described.items()
    ]

    return MappingProposal(
        import_id=import_id,
        fingerprint=profile.fingerprint,
        provider=proposal.provider if proposal else "unknown",
        sheets=sheets,
        problems=problems,
        usable=bool(sheets) and not problems,
    )


@router.post("/{import_id}/mapping/confirm", response_model=ImportRead)
async def confirm_column_mapping(import_id: str, request: MappingConfirmation) -> ImportRead:

    """Store a person's confirmed mapping as a reusable template and re extract this import with it."""

    record = await load_import(import_id, request.user_id)

    if not record.proposed_mapping:
        raise HTTPException(status_code=409, detail="this import has no layout to map")

    from app.extraction.workbook import WorkbookProfile
    from app.repositories.templates_repository import templates_repository

    profile = WorkbookProfile.model_validate(record.proposed_mapping["layout"])

    sheets = [
        {
            "name": sheet.sheet,
            "header_row": sheet.header_row,
            "asset_type": sheet.asset_type,
            "mapping": {field: [header] for field, header in sheet.mapping.items()},
        }
        for sheet in request.sheets
    ]

    async with session_scope() as session:
        await templates_repository.save(
            session,
            fingerprint=profile.fingerprint,
            name=request.name,
            provider=request.provider,
            sheets=sheets,
            created_by_user_id=request.user_id,
        )

    content = await document_storage.get(record.storage_key)

    await import_service.run_extraction(import_id, record.filename, record.content_type, content)

    return to_import_read(await load_import(import_id, request.user_id))
