"""The table models for uploaded files and the rows parsed from them before they reach the record tables."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import DocumentStatus, ImportRowAction, ImportRowStatus
from app.db.models.base import UserOwnedMixin, created_at_column, db_enum, updated_at_column
from app.db.session import Base


class Document(UserOwnedMixin, Base):

    """One file the user uploaded, kept once per user and hash, with the format family it matched."""

    __tablename__ = "documents"

    __table_args__ = (
        UniqueConstraint("user_id", "sha256", name="uq_documents_user_sha256"),
        Index("ix_documents_user_status", "user_id", "status"),
        )

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    family: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[DocumentStatus] = mapped_column(
        db_enum(DocumentStatus, "document_status"),
        nullable=False,
        server_default=DocumentStatus.uploaded.value,
        )
    error_message: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class LayoutMapping(Base):

    """One sheet shape, known by its headers, and the table and fields its columns go to, shared by every user."""

    __tablename__ = "layout_mappings"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    headers: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    target_table: Mapped[str | None] = mapped_column(String(50))
    columns: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    confirmed_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class ImportRow(UserOwnedMixin, Base):

    """One full record parsed from a document, with its source cells, checks, your edits and the values it replaced."""

    __tablename__ = "import_rows"

    __table_args__ = (
        UniqueConstraint("document_id", "row_number", name="uq_import_rows_document_row"),
        Index("ix_import_rows_document_status", "document_id", "status"),
        Index("ix_import_rows_user_id", "user_id"),
        )

    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    target_table: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[ImportRowAction | None] = mapped_column(db_enum(ImportRowAction, "import_row_action"))
    status: Mapped[ImportRowStatus] = mapped_column(
        db_enum(ImportRowStatus, "import_row_status"),
        nullable=False,
        server_default=ImportRowStatus.proposed.value,
        )
    parsed_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    edited_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    previous_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    target_record_id: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    errors: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    warnings: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    questions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    resolved: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    written_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
