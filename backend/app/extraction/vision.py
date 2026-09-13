"""Reading a scanned statement or a screenshot with a vision model, where there is no text layer to read."""

import base64
import io
from decimal import Decimal
from typing import Literal

import pdfplumber
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.config import settings
from app.extraction.bank_csv import guess_category, parse_amount, parse_date
from app.extraction.base import ExtractedRow, ExtractionResult
from app.services.llm_service import get_vision_model

IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)

WEBP_PREFIX = b"RIFF"

WEBP_TAG = b"WEBP"

VISION_SYSTEM_PROMPT = """You are reading a picture of a bank or card statement for the person whose account it is.

Copy what the image shows. Never complete a number you cannot fully see, never carry a figure over from
another line, and never invent a transaction to fill a gap. A row you cannot read is a row you leave out.

Report every money line you can read, one entry each, in the order they appear.
- occurred_on: the date exactly as printed, not reformatted.
- description: the narration or merchant text as printed.
- amount: digits and a decimal point only, no currency symbol and no thousands separators.
- direction: debit for money leaving the account, credit for money arriving.

Set document_kind to bank_statement, card_statement, holdings_statement or unknown.
Leave transactions empty if the image is not a statement at all."""

VISION_USER_PROMPT = "Read every transaction line in these pages."


class SeenTransaction(BaseModel):

    """One money line a vision model reports seeing, in the words the image used."""

    occurred_on: str
    description: str
    amount: str
    direction: Literal["debit", "credit"]


class SeenStatement(BaseModel):

    """Everything a vision model made of one document's pages, before any of it is trusted."""

    document_kind: str
    transactions: list[SeenTransaction] = Field(default_factory=list)


def image_media_type(head: bytes) -> str | None:

    """Name the image format from its leading bytes, so a renamed file is judged by content."""

    for signature, media_type in IMAGE_SIGNATURES:

        if head.startswith(signature):
            return media_type

    if head.startswith(WEBP_PREFIX) and head[8:12] == WEBP_TAG:
        return "image/webp"

    return None


def page_images(content: bytes, password: str | None = None) -> list[tuple[bytes, str]]:

    """Render a PDF's leading pages to PNG bytes, which is the only form a vision model can read them in."""

    rendered: list[tuple[bytes, str]] = []

    with pdfplumber.open(io.BytesIO(content), password=password or "") as document:

        for page in document.pages[: settings.maximum_vision_pages]:

            buffer = io.BytesIO()

            page.to_image(resolution=settings.vision_render_dpi).original.save(buffer, format="PNG")

            rendered.append((buffer.getvalue(), "image/png"))

    return rendered


def as_data_url(image: bytes, media_type: str) -> str:

    """Inline one rendered page as a data URL, since the model is sent bytes rather than a link."""

    return f"data:{media_type};base64,{base64.b64encode(image).decode()}"


async def read_pages(images: list[tuple[bytes, str]]) -> SeenStatement:

    """Ask the vision model what these pages say, returning nothing seen rather than raising."""

    if not images:
        return SeenStatement(document_kind="unknown")

    parts = [{"type": "text", "text": VISION_USER_PROMPT}]

    for image, media_type in images:
        parts.append({"type": "image_url", "image_url": {"url": as_data_url(image, media_type)}})

    model = get_vision_model().with_structured_output(SeenStatement)

    seen = await model.ainvoke([SystemMessage(VISION_SYSTEM_PROMPT), HumanMessage(parts)])

    return seen or SeenStatement(document_kind="unknown")


def to_rows(seen: SeenStatement) -> list[ExtractedRow]:

    """Turn what the model reported into staged rows, dropping credits and anything without an amount."""

    rows: list[ExtractedRow] = []

    for index, transaction in enumerate(seen.transactions, start=1):

        if transaction.direction == "credit":
            continue

        amount = parse_amount(transaction.amount)

        if amount is None:
            continue

        occurred_on, date_issue = parse_date(transaction.occurred_on)

        description = transaction.description.strip()

        confidence = Decimal("0.600")

        if date_issue:
            confidence = Decimal("0.350")

        elif not description:
            confidence = Decimal("0.450")

        rows.append(
            ExtractedRow(
                target_table="expense_transactions",
                payload={
                    "occurred_on": occurred_on,
                    "amount": str(amount),
                    "category": guess_category(description),
                    "merchant": description[:160],
                    "description": description[:500],
                },
                confidence=confidence,
                issue=date_issue or "read from an image, so check this line against the original",
                source_row_number=index,
                source_cells=[transaction.occurred_on, description, transaction.amount],
            )
        )

    return rows


async def extract_from_images(
    images: list[tuple[bytes, str]],
    extractor_name: str,
    detected_format: str,
    ) -> ExtractionResult:

    """Run one vision read over already rendered pages, which is what both a scan and a screenshot become."""

    try:
        seen = await read_pages(images)

    except Exception as exc:
        return ExtractionResult(
            extractor=extractor_name,
            detected_format=detected_format,
            document_kind="unknown",
            error=f"reading this image failed: {type(exc).__name__}",
        )

    rows = to_rows(seen)

    if not rows:
        return ExtractionResult(
            extractor=extractor_name,
            detected_format=detected_format,
            document_kind=seen.document_kind,
            error="no transactions could be read from this image",
        )

    return ExtractionResult(
        extractor=extractor_name,
        detected_format=detected_format,
        document_kind=seen.document_kind,
        rows=rows,
    )


class VisionExtractor:

    """Reads transactions from a photograph or screenshot of a statement, where nothing deterministic can."""

    name = "vision.v1"

    def can_handle(self, filename: str, content_type: str, head: bytes) -> bool:

        """Claim a document only when its leading bytes are an image format the model can be shown."""

        return image_media_type(head) is not None

    async def extract(
        self,
        content: bytes,
        filename: str,
        user_id: int,
        password: str | None = None,
        ) -> ExtractionResult:

        """Show this one image to the vision model and stage every debit line it reports reading."""

        media_type = image_media_type(content[:16])

        if media_type is None:
            return ExtractionResult(
                extractor=self.name,
                detected_format="unknown",
                document_kind="unknown",
                error="this file is not an image format that can be read",
            )

        return await extract_from_images([(content, media_type)], self.name, "image")
