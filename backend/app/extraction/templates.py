"""Template families: the mapping from one provider's column names to the common holdings model.

A parser per file would be unmaintainable; a parser per template family is not. A template says which
sheets hold holdings, where each header sits, which column means what, and where the statement states
its own totals. Everything else - reading cells, coercing values, computing what was not supplied -
is shared, so adding a provider is a data change rather than a code change.

Built in templates cover the formats already seen. Anything else goes to the mapping path: a person
confirms a proposed mapping once, it is stored with the layout's fingerprint, and the next file of
that shape is parsed deterministically without anyone being asked again. That is the whole point -
unknown formats are a one time cost, not a recurring one.

Column matching is by alias, not by position. Providers reorder columns between exports far more
readily than they rename them, and matching "Quantity Available", "Qty Available" and "Units" to the
same field is what makes a template survive a minor export change.

Totals are located in two shapes because statements use both. Some put a label in one cell and its
value in the next; others put labels across a row with values beneath. Both are scanned for, because
guessing wrong means reconciling against a number that is not the total.

A table's header row is skipped when looking for totals, and that is not a detail. A column headed
"Buy Value" is not a total labelled "Buy Value", and matching it adds one data row to the statement's
stated total - which showed up as a four percent reconciliation drift on a file that in fact
reconciled to the rupee. Summary lines carry a handful of populated cells; header rows carry many, so
a row wider than ``MAXIMUM_TOTALS_ROW_CELLS`` is not read as a summary.

A row whose first cell reads as a total is skipped, always. One of the three real formats ends with
a formula total row that would otherwise import as a holding worth the entire portfolio.
"""

from decimal import Decimal

from pydantic import BaseModel, Field

from app.extraction.holdings import CanonicalHolding, finalise
from app.extraction.values import clean_text, looks_like_total_row, to_date, to_decimal, to_money_value
from app.extraction.workbook import normalise_header

CANONICAL_FIELDS = (
    "instrument_name",
    "isin",
    "symbol",
    "quantity",
    "average_cost",
    "last_price",
    "invested_value",
    "current_value",
    "folio_id",
    "account_label",
    "source",
    "asset_type",
)

MONEY_FIELDS = frozenset({"average_cost", "last_price", "invested_value", "current_value"})

INVESTED_LABELS = ("invested value", "total investments", "total invested", "total buy value")
CURRENT_LABELS = ("current value", "present value", "current portfolio value", "total market value")

MAXIMUM_TOTALS_ROW_CELLS = 5


class SheetSpec(BaseModel):

    """How to read one sheet of a template: where its table is and what its columns mean."""

    name: str | None = None
    name_contains: str | None = None
    header_row: int | None = None
    asset_type: str = "unknown"
    account_label: str | None = None
    mapping: dict[str, list[str]] = Field(default_factory=dict)


class TemplateSpec(BaseModel):

    """One provider's layout family, identified by fingerprint and applied without further guessing."""

    id: str
    name: str
    provider: str
    document_kind: str = "holdings_statement"
    fingerprint: str | None = None
    sheets: list[SheetSpec] = Field(default_factory=list)
    builtin: bool = True


def matches_sheet(spec: SheetSpec, sheet_name: str) -> bool:

    """Decide whether one sheet spec applies to a sheet, by exact name or by a contained word."""

    if spec.name is not None:
        return normalise_header(spec.name) == normalise_header(sheet_name)

    if spec.name_contains is not None:
        return normalise_header(spec.name_contains) in normalise_header(sheet_name)

    return True


def resolve_columns(headers: list[str], mapping: dict[str, list[str]]) -> dict[str, int]:

    """Find which column index holds each canonical field, matching header aliases rather than positions."""

    normalised = [normalise_header(header) for header in headers]

    resolved: dict[str, int] = {}

    for field, aliases in mapping.items():

        for alias in aliases:

            target = normalise_header(alias)

            if target in normalised:
                resolved[field] = normalised.index(target)
                break

        if field in resolved:
            continue

        for index, header in enumerate(normalised):

            if header and any(normalise_header(alias) in header for alias in aliases):
                resolved[field] = index
                break

    return resolved


def cell(row: list, index: int | None) -> object:

    """Read one cell by resolved index, tolerating a short row rather than raising on it."""

    if index is None or index >= len(row):
        return None

    return row[index]


def build_holding(
    row: list,
    columns: dict[str, int],
    spec: SheetSpec,
    as_of,
    ) -> CanonicalHolding | None:

    """Turn one mapped spreadsheet row into a candidate holding, or skip it if it is not one."""

    name = clean_text(cell(row, columns.get("instrument_name")))

    symbol = clean_text(cell(row, columns.get("symbol"))) or name

    if not name and not symbol:
        return None

    isin = clean_text(cell(row, columns.get("isin"))) or None

    folio_id = clean_text(cell(row, columns.get("folio_id"))) or None

    from app.extraction.holdings import choose_identifier

    _, identifier_type = choose_identifier(isin, symbol, folio_id)

    holding = CanonicalHolding(
        instrument_name=name or symbol,
        isin=isin,
        symbol=symbol or None,
        identifier_type=identifier_type,
        asset_type=clean_text(cell(row, columns.get("asset_type"))).lower() or spec.asset_type,
        account_label=spec.account_label,
        folio_id=folio_id,
        source=clean_text(cell(row, columns.get("source"))) or None,
        quantity=to_decimal(cell(row, columns.get("quantity"))),
        average_cost=to_money_value(cell(row, columns.get("average_cost"))),
        last_price=to_money_value(cell(row, columns.get("last_price"))),
        invested_value=to_money_value(cell(row, columns.get("invested_value"))),
        current_value=to_money_value(cell(row, columns.get("current_value"))),
        as_of=as_of,
    )

    return finalise(holding)


def find_statement_totals(rows: list[list]) -> dict[str, Decimal]:

    """Locate the statement's own totals, trying both the label beside value and label above value shapes."""

    totals: dict[str, Decimal] = {}

    for index, row in enumerate(rows):

        cells = [clean_text(value) for value in row]

        if sum(1 for text in cells if text) > MAXIMUM_TOTALS_ROW_CELLS:
            continue

        for position, text in enumerate(cells):

            lowered = normalise_header(text)

            if not lowered:
                continue

            key = None

            if any(normalise_header(label) == lowered for label in INVESTED_LABELS):
                key = "invested_value"

            elif any(normalise_header(label) == lowered for label in CURRENT_LABELS):
                key = "current_value"

            if key is None or key in totals:
                continue

            beside = next((to_money_value(value) for value in row[position + 1 :] if clean_text(value)), None)

            if beside is not None:
                totals[key] = beside
                continue

            if index + 1 < len(rows):

                below = to_money_value(cell(rows[index + 1], position))

                if below is not None:
                    totals[key] = below

    return totals


def parse_with_template(
    template: TemplateSpec,
    sheets: dict[str, list[list]],
    as_of=None,
    ) -> tuple[list[tuple[str, int, list, CanonicalHolding]], dict[str, Decimal]]:

    """Apply a template to a workbook, returning candidate holdings with provenance and the stated totals."""

    results: list[tuple[str, int, list, CanonicalHolding]] = []

    totals: dict[str, Decimal] = {}

    for sheet_name, rows in sheets.items():

        sheet_totals = find_statement_totals(rows[:30])

        for key, value in sheet_totals.items():
            totals[key] = totals.get(key, Decimal("0")) + value

        spec = next((candidate for candidate in template.sheets if matches_sheet(candidate, sheet_name)), None)

        if spec is None:
            continue

        header_index = (spec.header_row or 1) - 1

        if header_index >= len(rows):
            continue

        headers = [clean_text(value) for value in rows[header_index]]

        columns = resolve_columns(headers, spec.mapping)

        if "instrument_name" not in columns and "symbol" not in columns:
            continue

        for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):

            if not any(clean_text(value) for value in row):
                continue

            if looks_like_total_row([clean_text(value) for value in row]):
                continue

            holding = build_holding(list(row), columns, spec, as_of)

            if holding is not None:
                results.append((sheet_name, offset, [clean_text(value) for value in row], holding))

    return results, totals
