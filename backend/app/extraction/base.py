"""The contract every document extractor satisfies, whatever technique it uses inside.

An extractor takes bytes and returns candidate rows. That is the whole interface, and it is
deliberately narrow so the choice between a deterministic parser, a PDF text layer reader and a
vision model is an implementation detail behind it rather than a fork in the pipeline.

Every returned row carries a ``confidence`` and, where relevant, an ``issue``. A deterministic
parser that matched a known column layout returns 1.0; anything that had to infer returns less,
and the reconciliation screen sorts by it so a person's attention goes where it is worth spending.
An extractor that cannot say how sure it is should return a low number rather than a default one.

``ExtractedRow.payload`` is shaped for the table it is destined for, not for the document it came
from. Mapping happens inside the extractor, where the source format is understood, rather than
downstream where it is not.

``can_handle`` is how the dispatcher chooses. It sees the filename, the content type and the first
bytes, which is enough to recognise a CSV header or a PDF producer string without reading the
whole file. An extractor that needs the entire document to decide should return False and let a
more general one take it.

No extractor writes anything. They return rows; the import service stages them; a person commits
them. That separation is why a wrong parser produces a rejected row rather than a wrong record.

``needs_mapping`` is the third outcome beside success and failure, and it is what makes an unknown
format a one time cost. An extractor that recognises a file as tabular holdings but does not know the
provider returns the layout it found instead of guessing at it; a person confirms a column mapping
once, and the next file of that shape is parsed deterministically.

``statement_totals`` carries what the document says about itself. Reconciling the sum of extracted
rows against the statement's own figure is the check that catches a missed column, a skipped sheet or
a total row imported as a holding - none of which are visible from the rows alone.
"""

from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field


class ExtractedRow(BaseModel):

    """One candidate record read from a document, with how sure the extractor is about it."""

    model_config = {"arbitrary_types_allowed": True}

    target_table: str
    payload: dict
    confidence: Decimal = Decimal("1.000")
    issue: str | None = None

    source_sheet: str | None = None
    source_row_number: int | None = None
    source_cells: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):

    """Everything one extractor made of one document, including a failure it could not recover from."""

    model_config = {"arbitrary_types_allowed": True}

    extractor: str
    detected_format: str
    document_kind: str
    rows: list[ExtractedRow] = Field(default_factory=list)
    error: str | None = None

    template_id: str | None = None
    statement_totals: dict[str, Decimal] = Field(default_factory=dict)
    needs_mapping: bool = False
    layout: dict | None = None


class DocumentExtractor(Protocol):

    """The interface the import pipeline depends on, hiding whether extraction is parsed or inferred."""

    name: str

    def can_handle(self, filename: str, content_type: str, head: bytes) -> bool: ...

    async def extract(self, content: bytes, filename: str, user_id: int) -> ExtractionResult: ...
