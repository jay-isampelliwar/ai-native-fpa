"""Tables for uploaded documents and the rows extracted from them before anyone commits them.

Extraction never writes to a record table. It writes here, to ``staged_rows``, where a person can
see what was read, correct it, and only then commit. That two step is the whole reason these
tables exist: a statement parser that was slightly wrong about a column would otherwise silently
put wrong transactions into someone's spending history, and no audit trail would show it as
anything other than data the user entered.

``DocumentImportRow.status`` is the state machine of one upload. ``uploaded`` means bytes are
stored and nothing has been read; ``extracting`` means a job is working; ``extracted`` means rows
are staged and awaiting a person; ``committed`` means they are in the record tables;  ``failed``
means the document could not be read and says why in ``error``.

``import_batch_id`` is set at commit, not at upload, and every record row written from this
document carries it. That is what makes a bad import reversible as a unit rather than row by row,
and it is why the field is nullable until the commit succeeds.

``StagedRow.payload`` is the record as extraction understood it, in the shape the target table
expects. It is JSON rather than typed columns because one import can produce transactions, another
holdings, and forcing both into one column set would mean a table of mostly nulls.

``confidence`` travels with each row so a reconciliation screen can put the doubtful ones first. A
deterministic parser reports one; an extraction that had to guess reports lower, and a person's
attention goes where it is worth spending.

``ImportTemplateRow`` is what makes an unfamiliar format a one time cost. Its ``fingerprint`` is a hash
of the layout - sheet names and header cells, never data - so the same export next month matches the
mapping a person already confirmed, and a different provider's file does not.

``StagedRowRow`` keeps the sheet, the row number and the raw cells alongside the parsed payload.
Reconciling a total that is off by one row means going back to the source line, and a payload alone
cannot say which line of which sheet produced it.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecordId

IMPORT_STATUSES = ("uploaded", "extracting", "extracted", "committed", "failed")

STAGED_ROW_STATUSES = ("pending", "accepted", "rejected", "duplicate")


class DocumentImportRow(Base):

    """One uploaded document and where it has reached between arriving and being committed."""

    __tablename__ = "document_imports"
    __table_args__ = (Index("ix_document_imports_user_created", "user_id", "created_at"),)

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)

    document_kind: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    detected_format: Mapped[str | None] = mapped_column(Text)
    extractor: Mapped[str | None] = mapped_column(Text)
    template_id: Mapped[str | None] = mapped_column(String(64))

    statement_totals: Mapped[dict | None] = mapped_column(JSONB)
    computed_totals: Mapped[dict | None] = mapped_column(JSONB)
    reconciled: Mapped[bool | None] = mapped_column(Boolean)
    reconciliation_note: Mapped[str | None] = mapped_column(Text)
    proposed_mapping: Mapped[dict | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="uploaded")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)

    import_batch_id: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    extracted_at: Mapped[datetime | None] = mapped_column()
    committed_at: Mapped[datetime | None] = mapped_column()


class StagedRowRow(Base):

    """One record extracted from a document, awaiting a person's decision before it is committed."""

    __tablename__ = "staged_rows"
    __table_args__ = (Index("ix_staged_rows_import_status", "import_id", "status"),)

    id: Mapped[RecordId]
    import_id: Mapped[str] = mapped_column(
        ForeignKey("document_imports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    target_table: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=1.0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    issue: Mapped[str | None] = mapped_column(Text)
    edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    committed_record_id: Mapped[str | None] = mapped_column(Text)

    source_sheet: Mapped[str | None] = mapped_column(Text)
    source_row_number: Mapped[int | None] = mapped_column(Integer)
    source_cells: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class ImportTemplateRow(Base):

    """A confirmed column mapping for one layout, so the next file of that shape needs no confirmation."""

    __tablename__ = "import_templates"

    id: Mapped[RecordId]
    name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    document_kind: Mapped[str] = mapped_column(Text, nullable=False, default="holdings_statement")

    fingerprint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    sheet_name: Mapped[str | None] = mapped_column(Text)
    header_row: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_data_row: Mapped[int | None] = mapped_column(Integer)

    column_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    totals_locator: Mapped[dict | None] = mapped_column(JSONB)

    builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger)
    times_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
