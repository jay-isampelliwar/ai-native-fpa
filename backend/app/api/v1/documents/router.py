"""The document import surface: upload, watch, unlock, approve or refuse, with nothing written until approved."""

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.api.v1.documents.schemas import (
    CommitResponse,
    DocumentRead,
    PasswordRequest,
    PendingDocuments,
    StagedRowRead,
    StagedRows,
    UploadedDocument,
    UploadResponse,
)
from app.core.config import settings
from app.services.import_service import import_service
from app.storage.files import document_storage

router = APIRouter(prefix="/documents", tags=["documents"])


def to_document_read(record, counts: dict[str, int]) -> DocumentRead:

    """Present one import row with its staged row tally, which is what a card needs before any detail."""

    return DocumentRead(
        id=record.id,
        filename=record.filename,
        content_type=record.content_type,
        byte_size=record.byte_size,
        status=record.status,
        document_kind=record.document_kind,
        detected_format=record.detected_format,
        extractor=record.extractor,
        error=record.error,
        row_count=record.row_count,
        pending_rows=counts.get("pending", 0),
        accepted_rows=counts.get("accepted", 0),
        rejected_rows=counts.get("rejected", 0),
        duplicate_rows=counts.get("duplicate", 0),
        statement_totals=record.statement_totals,
        computed_totals=record.computed_totals,
        reconciled=record.reconciled,
        reconciliation_note=record.reconciliation_note,
        import_batch_id=record.import_batch_id,
        created_at=record.created_at,
        extracted_at=record.extracted_at,
        committed_at=record.committed_at,
    )


def to_staged_row_read(row) -> StagedRowRead:

    """Present one staged row, unwrapping the source cells the extractor stored as an object."""

    source = row.source_cells or {}

    return StagedRowRead(
        id=row.id,
        row_index=row.row_index,
        target_table=row.target_table,
        payload=row.payload,
        confidence=row.confidence,
        status=row.status,
        issue=row.issue,
        edited=row.edited,
        source_sheet=row.source_sheet,
        source_row_number=row.source_row_number,
        source_cells=source.get("cells", []),
    )


async def owned_import(user_id: int, import_id: str):

    """Load an import for its owner or refuse, since not yours and not there are the same answer here."""

    record = await import_service.get_import(user_id, import_id)

    if record is None:
        raise HTTPException(status_code=404, detail="that document is not there")

    return record


@router.post("", response_model=UploadResponse)
async def upload_documents(
    user_id: int = Form(..., gt=0),
    files: list[UploadFile] = File(...),
    ) -> UploadResponse:

    """Store every uploaded file and start reading it, answering before any of them have been read."""

    if len(files) > settings.maximum_upload_files:
        raise HTTPException(
            status_code=400,
            detail=f"send at most {settings.maximum_upload_files} files at a time",
        )

    for upload in files:

        if upload.size is not None and upload.size > settings.maximum_upload_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"{upload.filename} is larger than {settings.maximum_upload_bytes // (1024 * 1024)}MB",
            )

    accepted: list[UploadedDocument] = []

    for upload in files:

        content = await upload.read()

        if len(content) > settings.maximum_upload_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"{upload.filename} is larger than {settings.maximum_upload_bytes // (1024 * 1024)}MB",
            )

        record, duplicate = await import_service.create_import(
            user_id,
            upload.filename or "document",
            upload.content_type or "application/octet-stream",
            content,
            document_storage,
        )

        if not duplicate:
            import_service.start_extraction(record.id, record.filename, record.content_type, content)

        accepted.append(
            UploadedDocument(
                id=record.id,
                filename=record.filename,
                status=record.status,
                duplicate=duplicate,
            )
        )

    return UploadResponse(documents=accepted)


@router.get("", response_model=PendingDocuments)
async def list_pending_documents(user_id: int = Query(..., gt=0)) -> PendingDocuments:

    """List every document still waiting on a decision, so a reopened tab does not lose an upload."""

    records = await import_service.list_pending(user_id)

    documents = [
        to_document_read(record, await import_service.counts_by_status(user_id, record.id))
        for record in records
    ]

    return PendingDocuments(documents=documents)


@router.get("/{import_id}", response_model=DocumentRead)
async def read_document(import_id: str, user_id: int = Query(..., gt=0)) -> DocumentRead:

    """Report where one document has reached, which is what the client polls while it is being read."""

    record = await owned_import(user_id, import_id)

    return to_document_read(record, await import_service.counts_by_status(user_id, import_id))


@router.get("/{import_id}/rows", response_model=StagedRows)
async def read_document_rows(import_id: str, user_id: int = Query(..., gt=0)) -> StagedRows:

    """List everything read from one document, which is the detail the review card shows."""

    await owned_import(user_id, import_id)

    rows = await import_service.list_rows(user_id, import_id)

    return StagedRows(import_id=import_id, rows=[to_staged_row_read(row) for row in rows])


@router.post("/{import_id}/password", response_model=DocumentRead)
async def unlock_document(import_id: str, request: PasswordRequest) -> DocumentRead:

    """Open a locked document with the password a person just sent, holding it only for this call."""

    record = await import_service.unlock(request.user_id, import_id, request.password, document_storage)

    if record is None:
        raise HTTPException(status_code=409, detail="that document is not waiting for a password")

    return to_document_read(record, await import_service.counts_by_status(request.user_id, import_id))


@router.post("/{import_id}/approve", response_model=CommitResponse)
async def approve_document(import_id: str, user_id: int = Query(..., gt=0)) -> CommitResponse:

    """Accept everything read from this document and write it, which is the one path data enters by."""

    record = await owned_import(user_id, import_id)

    if record.status not in {"extracted", "committed"}:
        raise HTTPException(status_code=409, detail=f"this document is {record.status}")

    await import_service.accept_all(user_id, import_id)

    return CommitResponse(**await import_service.commit(user_id, import_id))


@router.post("/{import_id}/approve-duplicates", response_model=CommitResponse)
async def approve_document_duplicates(import_id: str, user_id: int = Query(..., gt=0)) -> CommitResponse:

    """Write the rows held back as already present, which only the person can say are genuinely twice."""

    record = await owned_import(user_id, import_id)

    if record.status not in {"extracted", "committed"}:
        raise HTTPException(status_code=409, detail=f"this document is {record.status}")

    await import_service.accept_duplicates(user_id, import_id)

    return CommitResponse(**await import_service.commit(user_id, import_id))


@router.post("/{import_id}/reject", response_model=DocumentRead)
async def reject_document(import_id: str, user_id: int = Query(..., gt=0)) -> DocumentRead:

    """Refuse a whole document, keeping what was read as history and deleting only the stored file."""

    await owned_import(user_id, import_id)

    record = await import_service.reject_import(user_id, import_id, document_storage)

    if record is None:
        raise HTTPException(status_code=409, detail="a committed document cannot be rejected")

    return to_document_read(record, await import_service.counts_by_status(user_id, import_id))
