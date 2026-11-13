"""Checking rows against the totals a statement prints: total lines, labelled sums, opening and closing balances, and running balances."""

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.features.documents.fields import amount_fields
from app.features.documents.normalize import NotReadable, header_key, to_decimal
from app.features.documents.reader import Cell, Sheet


TOLERANCE = Decimal(1)

TOTAL_LINE = re.compile(r"^(grand |net |sub ?)?totals?( amount| value| \(.*\))?$")

LABELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("opening_balance", ("opening balance", "balance brought forward", "opening bal")),
    ("closing_balance", ("closing balance", "balance carried forward", "closing bal")),
    ("invested_value", ("invested value", "total investment", "total invested", "investment value", "cost value")),
    ("present_value", ("present value", "current value", "market value", "total value", "portfolio value")),
    )

PRINTED_METRICS = tuple(metric for metric, _ in LABELS)

METRIC_NAMES = {
    "opening_balance": "Opening balance",
    "closing_balance": "Closing balance",
    "invested_value": "Invested value",
    "present_value": "Present value",
    }


@dataclass
class Printed:

    """One total the file prints: what it is, the amount, and where it was found."""

    sheet: str
    metric: str
    value: str
    ref: str
    field: str | None = None

    def as_dict(self) -> dict[str, Any]:

        """The total as plain JSON for the document summary."""

        return {"sheet": self.sheet, "metric": self.metric, "value": self.value, "ref": self.ref, "field": self.field}


def is_total_line(cells: dict[str, Cell | None] | list[Cell | None]) -> bool:

    """Whether a row is a total line, such as 'Total' or 'Grand Total' with amounts beside it, judged by its first text cell."""

    values = list(cells.values() if isinstance(cells, dict) else cells)

    if not any(cell is not None and amount(cell.value) is not None for cell in values):
        return False

    for cell in values:

        if cell is not None and isinstance(cell.value, str) and cell.value.strip():
            return TOTAL_LINE.match(header_key(cell.value)) is not None

        if cell is not None:
            return False

    return False


def metric_of(label: Any) -> str | None:

    """The kind of printed total a label names, such as closing_balance for 'Closing Balance :'."""

    if not isinstance(label, str):
        return None

    text = header_key(label)

    for metric, words in LABELS:

        if any(text.startswith(word) for word in words):
            return metric

    return None


def amount(value: Any) -> Decimal | None:

    """A cell value as an amount, or None when it is not one."""

    if value is None or isinstance(value, bool):
        return None

    try:
        return to_decimal(value)

    except (NotReadable, ArithmeticError):
        return None


def labelled_totals(
    sheet: Sheet,
    indexes: range | list[int]
    ) -> list[Printed]:

    """Totals printed as a label and an amount on the same line, such as 'Closing Balance  2,45,000.00', in the given rows."""

    found = []

    for index in indexes:

        row = sheet.rows[index]

        for position, cell in enumerate(row):

            metric = metric_of(cell.value) if cell is not None else None

            if metric is None:
                continue

            following = next((other for other in row[position + 1:] if other is not None), None)
            value = amount(following.value) if following is not None else None

            if value is not None:
                found.append(Printed(sheet.name, metric, str(value), following.ref))
                break

    return found


def line_totals(
    sheet: Sheet,
    header_index: int,
    field_by_key: dict[str, str],
    positions: dict[str, int],
    table: str
    ) -> list[Printed]:

    """The amounts on a sheet's total lines, one printed total per amount column, such as the sum of 'Current Value'."""

    found = []
    amounts = set(amount_fields(table))

    for index in range(header_index + 1, len(sheet.rows)):

        row = sheet.rows[index]

        if not any(row) or not is_total_line(row):
            continue

        for key, field_name in field_by_key.items():

            position = positions.get(key)
            cell = row[position] if position is not None and position < len(row) else None
            value = amount(cell.value) if cell is not None else None

            if field_name in amounts and value is not None:
                found.append(Printed(sheet.name, "column_total", str(value), cell.ref, field_name))

    return found


def number(value: Any) -> Decimal:

    """A row's stored amount as a Decimal, zero when it is missing."""

    found = amount(value)

    return found if found is not None else Decimal(0)


def signed(row: dict[str, Any]) -> Decimal:

    """A transaction's effect on the balance: plus for money in, minus for money out."""

    value = number(row.get("amount"))

    return value if row.get("direction") == "inflow" else -value


def result(
    printed: dict[str, Any],
    label: str,
    expected: Decimal,
    found: Decimal
    ) -> dict[str, Any]:

    """One check: what the file prints, what the rows add up to, and whether they agree within the tolerance."""

    difference = (found - expected).quantize(Decimal("0.01"))

    return {
        "sheet": printed["sheet"],
        "label": label,
        "expected": str(expected.quantize(Decimal("0.01"))),
        "found": str(found.quantize(Decimal("0.01"))),
        "difference": str(difference),
        "ok": abs(difference) <= TOLERANCE,
        "ref": printed.get("ref"),
        }


def holding_sum(
    rows: list[dict[str, Any]],
    direct: str,
    units_times: str
    ) -> Decimal | None:

    """The sum of a holding amount, taken directly when every row has it, otherwise as units times a price, or None when neither works."""

    if rows and all(row.get(direct) is not None for row in rows):
        return sum((number(row[direct]) for row in rows), Decimal(0))

    if rows and all(row.get("units") is not None and row.get(units_times) is not None for row in rows):
        return sum((number(row["units"]) * number(row[units_times]) for row in rows), Decimal(0))

    return None


def check_sheet(
    sheet: str,
    rows: list[dict[str, Any]],
    printed: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:

    """Every check for one sheet's rows against the totals printed on it."""

    checks = []
    by_metric = {item["metric"]: item for item in printed if item["metric"] != "column_total"}

    for item in printed:

        if item["metric"] == "column_total" and item.get("field"):
            found = sum((number(row.get(item["field"])) for row in rows), Decimal(0))
            checks.append(result(item, f"Total of {item['field'].replace('_', ' ')}", Decimal(item["value"]), found))

    for metric, direct, units_times in (("invested_value", "invested_amount", "avg_buy_price"), ("present_value", "current_value", "current_price")):

        item = by_metric.get(metric)
        found = holding_sum(rows, direct, units_times) if item else None

        if item and found is not None:
            checks.append(result(item, METRIC_NAMES[metric], Decimal(item["value"]), found))

    opening = by_metric.get("opening_balance")
    closing = by_metric.get("closing_balance")
    moves = [row for row in rows if row.get("amount") is not None]

    if opening and closing and moves:
        found = Decimal(opening["value"]) + sum((signed(row) for row in moves), Decimal(0))
        checks.append(result(closing, "Opening balance + credits − debits = closing balance", Decimal(closing["value"]), found))

    checks.extend(running_balance(sheet, rows, opening))

    return checks


def balance_breaks(
    rows: list[dict[str, Any]],
    opening: Decimal | None
    ) -> list[tuple[int, Decimal, Decimal]]:

    """Each line where the last balance plus this line's amount is not this balance, as its place, the balance expected and the one printed."""

    breaks = []
    previous = opening

    for place, row in enumerate(rows):

        balance = amount(row.get("balance"))

        if balance is None:
            return []

        if previous is not None:

            expected = previous + signed(row)

            if abs(expected - balance) > TOLERANCE:
                breaks.append((place, expected, balance))

        previous = balance

    return breaks


def running_balance(
    sheet: str,
    rows: list[dict[str, Any]],
    opening: dict[str, Any] | None
    ) -> list[dict[str, Any]]:

    """Check a running balance column line by line, in file order or newest first, whichever the statement uses, naming the first line that breaks."""

    lines = [row for row in rows if row.get("balance") is not None and row.get("amount") is not None]

    if len(lines) < 2:
        return []

    start = Decimal(opening["value"]) if opening else None
    forward = balance_breaks(lines, start)
    backward = balance_breaks(list(reversed(lines)), None)
    breaks, ordered = (forward, lines) if len(forward) <= len(backward) else (backward, list(reversed(lines)))
    printed = {"sheet": sheet, "ref": None}

    if not breaks:
        return [{**result(printed, "Running balance", Decimal(0), Decimal(0)), "label": "Running balance, line by line"}]

    place, expected, balance = breaks[0]
    line = ordered[place].get("_line")
    where = f"line {line}" if line else f"entry {place + 1}"

    return [{
        **result(printed, f"Running balance breaks at {where}", expected, balance),
        "label": f"Running balance breaks at {where}: the last balance plus this line gives ₹{expected.quantize(Decimal('0.01'))}, the file says ₹{balance.quantize(Decimal('0.01'))}",
        }]


def check_totals(
    rows_by_sheet: dict[str, list[dict[str, Any]]],
    printed: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:

    """Every totals check across the document, sheet by sheet."""

    checks = []
    sheets = {item["sheet"] for item in printed} | set(rows_by_sheet)

    for sheet in sorted(sheets):
        checks.extend(check_sheet(sheet, rows_by_sheet.get(sheet, []), [item for item in printed if item["sheet"] == sheet]))

    return checks


def mismatch_key(checks: list[dict[str, Any]]) -> str | None:

    """A fingerprint of the checks that failed, so an 'Import anyway' holds only for the exact mismatch the user saw."""

    failed = [{key: item[key] for key in ("sheet", "label", "expected", "found")} for item in checks if not item["ok"]]

    if not failed:
        return None

    return hashlib.sha256(json.dumps(failed, sort_keys=True).encode()).hexdigest()


def is_summary_line(cells: dict[str, Cell | None] | list[Cell | None]) -> bool:

    """Whether a row is a total line or a labelled total such as 'Closing Balance', which is checked, never imported."""

    values = list(cells.values() if isinstance(cells, dict) else cells)
    first = next((cell for cell in values if cell is not None), None)

    if first is not None and metric_of(first.value) is not None and any(cell is not first and cell is not None and amount(cell.value) is not None for cell in values):
        return True

    return is_total_line(values)
