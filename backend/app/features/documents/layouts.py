"""Unknown sheet shapes: their fingerprint, the masked view the model sees, the model's mapping, and the checks on it."""

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.features.documents.fields import TABLE_FIELDS
from app.features.documents.normalize import header_key, to_decimal
from app.features.documents.parsing import (
    ParsedRow,
    RowBuilder,
    data_rows,
    find_header,
    guess_header,
    header_columns,
    )
from app.features.documents.reader import Sheet
from app.services.llm import llm_service


SAMPLE_CHARS = 40

ROW_KEY_FIELDS = {
    "users": ("name",),
    "family_members": ("name",),
    "income_sources": ("amount",),
    "expenses": ("amount",),
    "transactions": ("amount", "debit_amount", "credit_amount"),
    "holdings": ("security_name", "isin"),
    "sip_plans": ("amount",),
    "bank_accounts": ("balance",),
    "fixed_deposits": ("principal", "current_value"),
    "retirement_accounts": ("balance",),
    "physical_assets": ("current_value",),
    "loans": ("outstanding",),
    "credit_cards": ("outstanding",),
    "insurance_policies": ("cover_amount",),
    "goals": ("target_amount",),
    }

PROMPT = """You map the columns of one spreadsheet sheet from an Indian user's financial file to a database table.

You see only the header row and a few sample rows. Every digit in the samples is replaced with 9.

Rules:
- Pick the one table the rows belong to, or null when the sheet holds no records for any table.
- Map a header to a field only when you are sure. Leave a header out when unsure or when no field fits.
- Never map two headers to the same field.
- Use only the table and field names listed below, spelled exactly.
- For a bank statement, map withdrawal or debit columns to debit_amount and deposit or credit columns to credit_amount.
- Give a one-line reason.

Tables and their fields:
{catalog}
"""


class ColumnChoice(BaseModel):

    """One header and the field it goes to."""

    header: str = Field(description="The header text exactly as shown")
    field: str = Field(description="The field name in the chosen table")


class SheetMapping(BaseModel):

    """The model's answer for one sheet."""

    target_table: str | None = Field(description="The table name, or null when the sheet holds no records")
    columns: list[ColumnChoice] = Field(default_factory=list)
    reason: str = Field(description="One line on why this table and these columns")


@dataclass
class SheetLayout:

    """One sheet's header row and fingerprint, ready to look up or send to the model."""

    sheet: Sheet
    header_index: int
    headers: list[str]
    fingerprint: str


def layout_of(sheet: Sheet) -> SheetLayout | None:

    """The sheet's header row and fingerprint, or None when no row looks like headers."""

    header_index = guess_header(sheet)

    if header_index is None:
        return None

    headers = [str(value).strip() for value in sheet.row_values(header_index) if value is not None]

    return SheetLayout(sheet, header_index, headers, fingerprint(headers))


def fingerprint(headers: list[str]) -> str:

    """A hash of the tidied headers in order, the same for every file of this shape."""

    joined = "|".join(header_key(header) for header in headers)

    return hashlib.sha256(joined.encode()).hexdigest()


def masked_samples(layout: SheetLayout) -> list[list[str]]:

    """A few rows under the header with every digit turned into 9, and nothing from above the header."""

    samples = []
    limit = get_settings().MAPPING_SAMPLE_ROWS

    for index in range(layout.header_index + 1, len(layout.sheet.rows)):

        values = layout.sheet.row_values(index)

        if not any(value is not None for value in values):
            continue

        samples.append([re.sub(r"\d", "9", str(value))[:SAMPLE_CHARS] if value is not None else "" for value in values])

        if len(samples) >= limit:
            break

    return samples


def catalog_text() -> str:

    """The table and field list for the prompt."""

    return "\n".join(f"- {table}: {', '.join(fields)}" for table, fields in TABLE_FIELDS.items())


def layout_text(layout: SheetLayout) -> str:

    """The header row and masked samples as plain lines for the model."""

    lines = [f"Sheet: {layout.sheet.name}", "Headers: " + " | ".join(layout.headers)]

    for sample in masked_samples(layout):
        lines.append("Sample: " + " | ".join(sample))

    return "\n".join(lines)


async def propose_mapping(layout: SheetLayout) -> SheetMapping:

    """Ask the model which table and fields this sheet's columns go to."""

    model = llm_service.get_model(get_settings().MAPPING_MODEL).with_structured_output(
        SheetMapping,
        method="function_calling",
        )

    return await model.ainvoke([
        ("system", PROMPT.format(catalog=catalog_text())),
        ("user", layout_text(layout)),
        ])


def mapping_errors(
    target_table: str | None,
    columns: dict[str, str],
    headers: list[str]
    ) -> list[str]:

    """Every reason a mapping cannot be trusted: unknown table or field, a missing header, a field used twice, no key field."""

    if target_table is None:
        return [] if not columns else ["A sheet with no table cannot map any columns"]

    if target_table not in TABLE_FIELDS:
        return [f"'{target_table}' is not a table a file can fill"]

    errors = []
    known_headers = {header_key(header) for header in headers}
    fields = TABLE_FIELDS[target_table]

    for header, field_name in columns.items():

        if header_key(header) not in known_headers:
            errors.append(f"Header '{header}' is not in the sheet")

        if field_name not in fields:
            errors.append(f"'{field_name}' is not a field of {target_table}")

    used = list(columns.values())

    for field_name in sorted({name for name in used if used.count(name) > 1}):
        errors.append(f"'{field_name}' is mapped from more than one header")

    if not set(ROW_KEY_FIELDS[target_table]) & set(used):
        errors.append(f"No column maps to {' or '.join(ROW_KEY_FIELDS[target_table])}, so rows cannot be read")

    return errors


def parse_mapped(
    sheet: Sheet,
    headers: list[str],
    target_table: str,
    columns: dict[str, str]
    ) -> list[ParsedRow]:

    """Read a sheet with a confirmed mapping, one row per line under the header."""

    header_index = find_header(sheet, {header_key(header) for header in headers})

    if header_index is None:
        return []

    positions = header_columns(sheet, header_index)
    field_by_key = {header_key(header): field_name for header, field_name in columns.items() if header_key(header) in positions}
    rows = []

    for row_number, cells in data_rows(sheet, header_index):

        builder = RowBuilder(target_table, sheet, row_number)

        for key, field_name in field_by_key.items():
            builder.put(field_name, cells.get(key))

        if target_table == "transactions":
            settle_direction(builder.row)

        if builder.has_content():
            rows.append(builder.row)

    return rows


def settle_direction(row: ParsedRow) -> None:

    """Turn a bank statement's separate debit and credit columns into one amount and its direction."""

    debit = row.data.pop("debit_amount", None)
    credit = row.data.pop("credit_amount", None)

    if "amount" in row.data:
        return

    debit_value = to_decimal(debit) if debit is not None else 0
    credit_value = to_decimal(credit) if credit is not None else 0

    if debit_value and credit_value:
        row.errors.append("amount: the line has both a debit and a credit")
        return

    if debit_value:
        row.data["amount"] = debit
        row.data["direction"] = "outflow"

    elif credit_value:
        row.data["amount"] = credit
        row.data["direction"] = "inflow"


def columns_of(mapping: SheetMapping) -> dict[str, str]:

    """The model's column list as a header-to-field map."""

    return {choice.header: choice.field for choice in mapping.columns}


def as_proposal(
    layout: SheetLayout,
    target_table: str | None,
    columns: dict[str, Any],
    reason: str | None
    ) -> dict[str, Any]:

    """One pending mapping as plain JSON for the document summary and the API."""

    return {
        "sheet": layout.sheet.name,
        "fingerprint": layout.fingerprint,
        "headers": layout.headers,
        "target_table": target_table,
        "columns": columns,
        "reason": reason,
        "errors": mapping_errors(target_table, columns, layout.headers),
        }
