"""Request and response shapes for the document routes."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.enums import DocumentStatus, ImportRowAction, ImportRowStatus


class ImportRowOut(BaseModel):

    """One parsed record as the review screen shows it."""

    id: int
    row_number: int
    target_table: str
    action: ImportRowAction | None
    status: ImportRowStatus
    parsed_data: dict[str, Any]
    edited_data: dict[str, Any] | None
    source: dict[str, Any]
    errors: list[Any]
    warnings: list[Any]
    questions: list[Any]
    resolved: dict[str, Any]


class DocumentOut(BaseModel):

    """One uploaded file, what each sheet gave, any mapping waiting for the user, and its parsed rows."""

    id: int
    original_filename: str
    family: str | None
    status: DocumentStatus
    error_message: str | None
    duplicate: bool = False
    sheets: list[dict[str, Any]] = Field(default_factory=list)
    checks: dict[str, int] = Field(default_factory=dict)
    pending_mappings: list[dict[str, Any]] = Field(default_factory=list)
    rows: list[ImportRowOut] = Field(default_factory=list)
    created_at: datetime


class DocumentListItem(BaseModel):

    """One uploaded file in the user's list."""

    id: int
    original_filename: str
    family: str | None
    status: DocumentStatus
    row_count: int
    created_at: datetime


class SheetChoice(BaseModel):

    """The user's mapping for one sheet: its table, or null to skip it, and the header-to-field columns."""

    sheet: str
    target_table: str | None
    columns: dict[str, str] = Field(default_factory=dict)


class ConfirmMapping(BaseModel):

    """The mappings the user confirms; sheets left out keep the model's proposal."""

    sheets: list[SheetChoice] = Field(default_factory=list)


class AnswerIn(BaseModel):

    """The user's answer to one question on one row."""

    row_id: int
    question_id: str
    answer: str


class AnswerQuestions(BaseModel):

    """One or more answers, sent as the user picks them on the review screen or in chat."""

    answers: list[AnswerIn] = Field(min_length=1)


class RowEdit(BaseModel):

    """The user's changes to one row: any field by name, and for a holding the stock or fund picked from the search."""

    changes: dict[str, Any] = Field(default_factory=dict)
    instrument: str | None = Field(default=None, description="A pick from the search, such as fund:123 or stock:45")


class InstrumentChoice(BaseModel):

    """One stock or fund suggested while the user types a name."""

    value: str
    label: str
    kind: str
    isin: str
    name: str


class ApprovalOutcome(BaseModel):

    """How many rows one approval wrote, found unchanged, or could not write, and the document after it."""

    written: int
    no_change: int
    failed: int
    document: DocumentOut
