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


class DocumentOut(BaseModel):

    """One uploaded file, what each sheet gave, any mapping waiting for the user, and its parsed rows."""

    id: int
    original_filename: str
    family: str | None
    status: DocumentStatus
    error_message: str | None
    duplicate: bool = False
    sheets: list[dict[str, Any]] = Field(default_factory=list)
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
