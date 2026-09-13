"""The HTTP shapes of the document import surface, kept separate from the ORM rows they are built from."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class UploadedDocument(BaseModel):

    """One accepted upload, named by the id a client polls and whether this file was already imported."""

    id: str
    filename: str
    status: str
    duplicate: bool = False


class UploadResponse(BaseModel):

    """Every file from one upload, answered before any of them have been read."""

    documents: list[UploadedDocument] = Field(default_factory=list)


class DocumentRead(BaseModel):

    """Where one document has reached, with enough about it to render a card without fetching its rows."""

    id: str
    filename: str
    content_type: str
    byte_size: int

    status: str
    document_kind: str
    detected_format: str | None = None
    extractor: str | None = None
    error: str | None = None

    row_count: int = 0
    pending_rows: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    duplicate_rows: int = 0

    statement_totals: dict | None = None
    computed_totals: dict | None = None
    reconciled: bool | None = None
    reconciliation_note: str | None = None

    import_batch_id: str | None = None
    created_at: datetime
    extracted_at: datetime | None = None
    committed_at: datetime | None = None


class PendingDocuments(BaseModel):

    """Everything still waiting on a person, which is what a reopened tab asks for on load."""

    documents: list[DocumentRead] = Field(default_factory=list)


class StagedRowRead(BaseModel):

    """One extracted record as the review card shows it, with where in the document it came from."""

    id: str
    row_index: int
    target_table: str
    payload: dict

    confidence: Decimal
    status: str
    issue: str | None = None
    edited: bool = False

    source_sheet: str | None = None
    source_row_number: int | None = None
    source_cells: list[str] = Field(default_factory=list)


class StagedRows(BaseModel):

    """Everything staged from one document, in the order the document stated it."""

    import_id: str
    rows: list[StagedRowRead] = Field(default_factory=list)


class PasswordRequest(BaseModel):

    """The password for a locked document, sent to open it and never stored anywhere."""

    user_id: int = Field(gt=0)
    password: str = Field(min_length=1, max_length=200)


class CommitResponse(BaseModel):

    """What one approval wrote, what it could not write, and the batch every record it created carries."""

    status: str
    rows_written: int = 0
    rows_skipped: int = 0
    import_batch_id: str | None = None
    detail: str | None = None
