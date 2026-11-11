"""The document routes: upload a file, list and read uploads, and confirm a mapping for an unknown format."""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.db.models import Document
from app.db.session import get_session
from app.features.documents.reader import UnreadableFile
from app.features.documents.repository import DocumentRepository
from app.features.documents.matching import suggest_instruments
from app.features.documents.schemas import (
    AnswerQuestions,
    ApprovalOutcome,
    ConfirmMapping,
    DocumentListItem,
    DocumentOut,
    ImportRowOut,
    InstrumentChoice,
    RowEdit,
    )
from app.features.documents.writer import UndoBlocked
from app.features.records.exceptions import RecordError
from app.features.documents.service import (
    AnswerInvalid,
    DocumentNotFound,
    EditInvalid,
    NothingToApprove,
    NothingToUndo,
    DocumentService,
    DocumentTooLarge,
    MappingInvalid,
    MappingNotExpected,
    )


router = APIRouter(prefix="/documents", tags=["documents"])


async def document_out(
    session: AsyncSession,
    document: Document,
    duplicate: bool = False
    ) -> DocumentOut:

    """The full view of one document with its sheet notes, pending mappings and rows."""

    rows = await DocumentRepository(session).rows(document.id)

    return DocumentOut(
        id=document.id,
        original_filename=document.original_filename,
        family=document.family,
        status=document.status,
        error_message=document.error_message,
        duplicate=duplicate,
        sheets=document.summary.get("sheets", []),
        checks=document.summary.get("checks", {}),
        pending_mappings=document.summary.get("pending_mappings", []),
        rows=[ImportRowOut.model_validate(row, from_attributes=True) for row in rows],
        created_at=document.created_at,
        )


@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
    ) -> DocumentOut:

    """Upload one .xlsx, .xls or .csv file and get back its parsed rows, or the mappings waiting for confirmation."""

    limit = get_settings().MAX_DOCUMENT_BYTES
    data = await file.read(limit + 1)

    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty")

    try:
        document, duplicate = await DocumentService(session).upload(user_id, file.filename or "upload", data)

    except DocumentTooLarge as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc

    except UnreadableFile as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    return await document_out(session, document, duplicate)


@router.get("/instruments/search")
async def search_instruments(
    q: str = Query(min_length=1, max_length=100),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
    ) -> list[InstrumentChoice]:

    """Stocks and funds for a name being typed in the review screen, closest first, from two letters on."""

    return [InstrumentChoice(**item) for item in await suggest_instruments(session, q)]


@router.get("")
async def list_documents(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
    ) -> list[DocumentListItem]:

    """The user's uploads, newest first."""

    documents = await DocumentRepository(session).list_for_user(user_id)

    return [
        DocumentListItem(
            id=document.id,
            original_filename=document.original_filename,
            family=document.family,
            status=document.status,
            row_count=document.summary.get("row_count", 0),
            created_at=document.created_at,
            )
        for document in documents
        ]


@router.get("/{document_id}")
async def get_document(
    document_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
    ) -> DocumentOut:

    """One upload with its sheet notes, pending mappings and parsed rows."""

    try:
        document = await DocumentService(session).get(user_id, document_id)

    except DocumentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    return await document_out(session, document)


@router.post("/{document_id}/mapping")
async def confirm_mapping(
    document_id: int,
    body: ConfirmMapping,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
    ) -> DocumentOut:

    """Confirm the mappings for an unknown format, changing any sheet's table or columns, then parse the file with them."""

    try:
        document = await DocumentService(session).confirm_mapping(user_id, document_id, body.sheets)

    except DocumentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    except MappingNotExpected as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    except MappingInvalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.errors) from exc

    return await document_out(session, document)


@router.post("/{document_id}/answers")
async def answer_questions(
    document_id: int,
    body: AnswerQuestions,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
    ) -> DocumentOut:

    """Save answers to row questions, such as which fund a name means, and get the document back checked again."""

    try:
        document = await DocumentService(session).answer(user_id, document_id, body.answers)

    except DocumentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    except AnswerInvalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.errors) from exc

    return await document_out(session, document)


@router.patch("/{document_id}/rows/{row_id}")
async def edit_row(
    document_id: int,
    row_id: int,
    body: RowEdit,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
    ) -> DocumentOut:

    """Change any field of one row, or pick its stock or fund, and get the document back checked again."""

    try:
        document = await DocumentService(session).edit(user_id, document_id, row_id, body)

    except DocumentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    except EditInvalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.errors) from exc

    return await document_out(session, document)


@router.post("/{document_id}/approve")
async def approve_document(
    document_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
    ) -> ApprovalOutcome:

    """Write every ready row into the record tables, each checked after saving; rows that fail are marked with the reason."""

    try:
        outcome = await DocumentService(session).approve(user_id, document_id)
        document = await DocumentService(session).get(user_id, document_id)

    except DocumentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    except NothingToApprove as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    return ApprovalOutcome(**outcome, document=await document_out(session, document))


@router.post("/{document_id}/undo")
async def undo_document(
    document_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
    ) -> DocumentOut:

    """Undo everything this document wrote, or nothing when a record was changed after the import."""

    service = DocumentService(session)

    try:
        await service.undo(user_id, document_id)

    except DocumentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    except NothingToUndo as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    except UndoBlocked as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.reasons) from exc

    except RecordError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    return await document_out(session, await service.get(user_id, document_id))
