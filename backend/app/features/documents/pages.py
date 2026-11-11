"""Reading pages only the model can read, scanned pages, photos and text with no table, into rows that code then cleans."""

import asyncio
import base64
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.features.documents.fields import TABLE_FIELDS, mappable_fields
from app.features.documents.parsing import ParsedRow, RowBuilder, SheetNote
from app.features.documents.reader import Cell, Page, Sheet
from app.features.documents.totals import PRINTED_METRICS, Printed, amount
from app.services.llm import llm_service


log = logging.getLogger(__name__)

PAGE_CONCURRENCY = 4

MODEL_WARNING = "Read by the model from page {number}. Check each value against the file before importing."

PROMPT = """You read one page of an Indian user's financial document and list the records on it.

Rules:
- List only records that are clearly on the page: holdings, transactions, balances, deposits, loans, policies and so on.
- Copy each value exactly as printed, including commas, signs and dates as shown. Never work out or round a value.
- Leave out totals, subtotals, page headers and anything you are not sure of.
- Use only the table and field names listed below, spelled exactly. Leave out a field when it is not on the page.
- When nothing on the page is a record, return no rows.
- Put totals the page prints in totals, never in rows, using only these names: {totals}.

Tables and their fields:
{catalog}
"""


class FieldValue(BaseModel):

    """One field of one record, with its value copied as printed."""

    name: str
    value: str


class PageRecord(BaseModel):

    """One record the model found on the page."""

    target_table: str
    fields: list[FieldValue] = Field(default_factory=list)


class PageReading(BaseModel):

    """Everything the model found on one page, its records and the totals it prints."""

    rows: list[PageRecord] = Field(default_factory=list)
    totals: list[FieldValue] = Field(default_factory=list)


def catalog() -> str:

    """The tables and fields the model may use."""

    return "\n".join(f"- {table}: {', '.join(mappable_fields(table))}" for table in TABLE_FIELDS)


def page_message(page: Page) -> HumanMessage:

    """The page as the model sees it: its text, or its picture."""

    if page.image is None:
        return HumanMessage(content=f"Page {page.number} text:\n\n{page.text}")

    encoded = base64.b64encode(page.image).decode()

    return HumanMessage(content=[
        {"type": "text", "text": f"Page {page.number} picture:"},
        {"type": "image_url", "image_url": {"url": f"data:{page.mime_type};base64,{encoded}"}},
        ])


async def read_page(page: Page) -> PageReading:

    """Ask the model for the records on one page."""

    settings = get_settings()
    model = llm_service.get_model(settings.PAGE_MODEL or settings.MAPPING_MODEL).with_structured_output(
        PageReading,
        method="function_calling",
        )

    prompt = PROMPT.format(catalog=catalog(), totals=", ".join(PRINTED_METRICS))

    return await model.ainvoke([SystemMessage(content=prompt), page_message(page)])


def rows_of(
    page: Page,
    reading: PageReading
    ) -> list[ParsedRow]:

    """Clean the model's values with the same rules as a spreadsheet cell, marking every row as read by the model."""

    sheet = Sheet(name=f"Page {page.number}")
    rows = []

    for position, record in enumerate(reading.rows, start=1):

        if record.target_table not in TABLE_FIELDS:
            continue

        allowed = set(mappable_fields(record.target_table))
        builder = RowBuilder(record.target_table, sheet, position)
        builder.row.source["read_by_model"] = True

        for item in record.fields:

            if item.name in allowed:
                builder.put(item.name, Cell(item.value, f"page {page.number}, record {position}"))

        builder.warn(MODEL_WARNING.format(number=page.number))

        if builder.has_content():
            rows.append(builder.row)

    return rows


def totals_of(
    page: Page,
    reading: PageReading
    ) -> list[dict[str, Any]]:

    """The totals the model copied from a page, kept only when the name is known and the value is an amount."""

    found = []

    for item in reading.totals:

        value = amount(item.value)

        if item.name in PRINTED_METRICS and value is not None:
            found.append(Printed(f"Page {page.number}", item.name, str(value), f"page {page.number}").as_dict())

    return found


async def read_pages(pages: list[Page]) -> tuple[list[ParsedRow], list[SheetNote], list[dict[str, Any]]]:

    """Read every page with the model, a few at a time, and note what each gave and the totals it prints."""

    limit = asyncio.Semaphore(PAGE_CONCURRENCY)

    async def one(page: Page) -> tuple[Page, PageReading]:

        """Read one page under the shared limit."""

        async with limit:
            return page, await read_page(page)

    readings = await asyncio.gather(*(one(page) for page in pages))
    rows: list[ParsedRow] = []
    notes: list[SheetNote] = []
    printed: list[dict[str, Any]] = []

    for page, reading in readings:

        found = rows_of(page, reading)
        printed.extend(totals_of(page, reading))
        rows.extend(found)
        how = "picture" if page.image is not None else "text"
        message = f"{len(found)} rows read by the model from the page {how}" if found else f"The model found no records in the page {how}"
        notes.append(SheetNote(f"Page {page.number}", "imported" if found else "empty", message, len(found)))

    return rows, notes, printed


def page_summary(pages: list[Page]) -> dict[str, Any]:

    """How many pages the model would read, and how many are pictures, for the consent step."""

    return {"count": len(pages), "pictures": sum(1 for page in pages if page.image is not None)}
