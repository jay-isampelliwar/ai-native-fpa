"""Request and response shapes for uploading documents and reconciling what was read from them.

``ImportRead`` reports a status rather than a percentage. Extraction either has not started, is
running, produced rows, failed, or has been committed, and those five states are what a client
needs to render. A progress bar over a job whose length is unknown is a lie with a number on it.

``StagedRowRead`` returns the payload as it currently stands plus its confidence and issue. Sorting
a reconciliation screen by confidence is the whole point of carrying it, so it is not optional and
not hidden behind a second call.

``StagedRowUpdate`` makes every field optional because a person correcting an import fixes one cell
at a time. Sending the whole row back would overwrite an earlier correction with whatever the
client last read.

``CommitResponse`` returns the ``import_batch_id``. That string is what tags every record written
from this document, so a client can offer to reverse the import and a support conversation can
identify it precisely.

Nothing here accepts a target table from the client. What a row becomes was decided by the
extractor that understood the source format; letting a request choose would let a caller write a
transaction into a holdings table.

The mapping schemas carry the one path where a model contributes to an import. A proposal is a
suggestion attached to one upload; it becomes a reusable template only when a person confirms it, and
``problems`` is returned alongside so a person is judging a validated mapping rather than catching a
broken one.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ImportRead(BaseModel):

    """One upload and where it has reached between arriving and being committed."""

    id: str
    filename: str
    status: str
    document_kind: str
    detected_format: str | None = None
    extractor: str | None = None
    template_id: str | None = None
    row_count: int = 0
    error: str | None = None
    import_batch_id: str | None = None
    created_at: datetime
    extracted_at: datetime | None = None
    committed_at: datetime | None = None
    duplicate_of_existing_upload: bool = False

    statement_totals: dict | None = None
    computed_totals: dict | None = None
    reconciled: bool | None = None
    reconciliation_note: str | None = None


class StagedRowRead(BaseModel):

    """One extracted record awaiting a decision, with how sure extraction was about it."""

    id: str
    row_index: int
    target_table: str
    payload: dict
    confidence: Decimal
    status: str
    issue: str | None = None
    edited: bool = False


class StagedRowsPage(BaseModel):

    """The staged rows of one import, with the counts a reconciliation screen shows at the top."""

    import_id: str
    status: str
    total: int
    pending: int
    accepted: int
    rejected: int
    duplicates: int
    rows: list[StagedRowRead] = Field(default_factory=list)


class StagedRowUpdate(BaseModel):

    """A correction to one staged row, applied field by field rather than as a whole replacement."""

    occurred_on: date | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    merchant: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=500)


class RowDecision(BaseModel):

    """Accept or reject one staged row, which is what the commit later acts on."""

    status: str = Field(pattern="^(accepted|rejected|pending)$")


class BulkDecision(BaseModel):

    """Accept or reject every row of an import at once, the common case for a clean statement."""

    status: str = Field(pattern="^(accepted|rejected)$")
    only_pending: bool = True


class CommitResponse(BaseModel):

    """What a commit did, including the batch id that tags every record it wrote."""

    status: str
    import_batch_id: str | None = None
    rows_written: int = 0
    detail: str | None = None


class MappingColumn(BaseModel):

    """One column of an unrecognised layout, offered for mapping with masked sample values."""

    index: int
    header: str
    samples: list[str] = Field(default_factory=list)


class MappingSheet(BaseModel):

    """One sheet of an unrecognised layout, and the mapping proposed for its columns."""

    sheet: str
    header_row: int
    asset_type: str = "unknown"
    columns: list[MappingColumn] = Field(default_factory=list)
    mapping: dict[str, str] = Field(default_factory=dict)


class MappingProposal(BaseModel):

    """A suggested mapping for a layout nobody has confirmed yet, with anything wrong with it."""

    import_id: str
    fingerprint: str
    provider: str = "unknown"
    sheets: list[MappingSheet] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    usable: bool = False


class MappingConfirmation(BaseModel):

    """A person's confirmed mapping, which becomes the template every later file of this shape uses."""

    user_id: int
    provider: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    sheets: list[MappingSheet] = Field(min_length=1)
