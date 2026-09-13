"""Choosing which extractor reads a document, and refusing clearly when none can.

Extractors are tried in registration order and the first that claims the document wins. Order
therefore encodes precedence: specific, deterministic parsers are registered before general ones,
so a CSV that a bank parser recognises is never handed to something that would have to infer.

An unrecognised document is a refusal, not a fallback. Guessing at an unknown layout produces rows
that look plausible and are wrong, which is worse than telling a user their format is not supported
yet - they can send a different export, and we learn which format to add.

The registry is explicit rather than discovered from the filesystem, for the same reason the skill
registry is: what a system will attempt to read should be a list a reviewer can see, not a
consequence of which modules happen to be importable.

Only the first bytes are handed to ``can_handle``. Deciding a format should not require reading a
forty megabyte statement into memory, and an extractor that genuinely needs the whole document
should decline and let something more general take it.

Four extractors are registered: a deterministic bank CSV parser, a PDF reader that uses the document's
own text layer, a workbook reader that dispatches to template families, and a vision reader for images.
Further formats slot in here without any other file changing, and the technique each uses is its own.

The workbook extractor is last because it claims broadly - any spreadsheet - while the CSV parser
claims narrowly. Ordering specific before general is what stops a broad extractor from swallowing a
file a precise one would have read correctly.
"""

from app.extraction.base import DocumentExtractor, ExtractionResult
from app.extraction.bank_csv import BankCsvExtractor
from app.extraction.holdings_extractor import HoldingsWorkbookExtractor
from app.extraction.pdf_text import PdfTextExtractor
from app.extraction.vision import VisionExtractor

HEAD_BYTES = 4096

EXTRACTORS: list[DocumentExtractor] = [
    BankCsvExtractor(),
    PdfTextExtractor(),
    HoldingsWorkbookExtractor(),
    VisionExtractor(),
]


def choose_extractor(filename: str, content_type: str, content: bytes) -> DocumentExtractor | None:

    """Find the first registered extractor that claims this document, or none if the format is unknown."""

    head = content[:HEAD_BYTES]

    for extractor in EXTRACTORS:

        if extractor.can_handle(filename, content_type, head):
            return extractor

    return None

async def extract_document(
    filename: str,
    content_type: str,
    content: bytes,
    user_id: int,
    password: str | None = None,
    ) -> ExtractionResult:

    """Dispatch a document to its extractor, returning a stated refusal when no format matches."""

    extractor = choose_extractor(filename, content_type, content)

    if extractor is None:
        return ExtractionResult(
            extractor="none",
            detected_format="unknown",
            document_kind="unknown",
            error="this document format is not supported yet",
        )

    return await extractor.extract(content, filename, user_id, password)
