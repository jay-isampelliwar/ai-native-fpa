"""Typed UI blocks built in code from exact tool data, so the chat can draw a card instead of a markdown table."""

import functools
import logging
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from app.agent.cards import generic_describe, humanize, plain_number, rupees
from app.features.analysis.service import GoalProgress
from app.features.records.kinds import RecordKind


MAX_COLUMNS = 6

TOP_SECTORS = 8

TOP_COMPARE_SECTORS = 5

FULL = 100.0


type Block = dict[str, Any]

log = logging.getLogger(__name__)


def never_fails[**P](builder: Callable[P, Block | None]) -> Callable[P, Block | None]:

    """Wrap a card builder so a bad row costs only the card, never the tool's answer."""

    @functools.wraps(builder)
    def safe(*args: P.args, **kwargs: P.kwargs) -> Block | None:

        """Build the card, or log and return None when building it breaks."""

        try:
            return builder(*args, **kwargs)

        except Exception:

            log.exception("could not build the %s card", builder.__name__)

            return None

    return safe


def word(value: Any) -> str:

    """An enum, date or plain value as short words for a card, with a dash when it is empty."""

    if value is None or value == "":
        return "—"

    if isinstance(value, Enum):
        return humanize(str(value.value))

    if isinstance(value, date):
        return f"{value.day} {value:%b %Y}"

    if isinstance(value, str) and value.isidentifier() and value == value.lower():
        return humanize(value)

    return str(value)


def money(value: Any) -> str:

    """A rupee amount for a card, or a dash when it is not known."""

    if value is None:
        return "—"

    return rupees(Decimal(str(value)))


def price(value: Any) -> str:

    """A share price or NAV for a card, with paise, or a dash when it is not known."""

    if value is None:
        return "—"

    return rupees(Decimal(str(value)), 2)


def pct(value: Any) -> str:

    """A percent for a card, such as 12.5%."""

    if value is None:
        return "—"

    return f"{plain_number(Decimal(str(value)))}%"


def column(
    label: str,
    numeric: bool = False,
    ) -> dict[str, Any]:

    """One table column, right-aligned when it holds numbers."""

    return {"key": label, "label": label, "align": "right" if numeric else "left"}


def looks_numeric(text: str) -> bool:

    """True when a cell reads as a number or an amount, so its column lines up on the right."""

    cleaned = text.lstrip("-₹").replace(",", "").rstrip("%")

    return bool(cleaned) and cleaned.replace(".", "", 1).isdigit()


def table(
    title: str,
    rows: list[dict[str, str]],
    subtitle: str | None = None,
    ) -> Block:

    """A table block whose columns come from the row keys in first-seen order, numbers on the right."""

    keys: list[str] = []

    for row in rows:

        for key in row:

            if key not in keys:
                keys.append(key)

    keys = keys[:MAX_COLUMNS]

    columns = [
        column(key, all(looks_numeric(row[key]) for row in rows if row.get(key) not in (None, "—")))
        for key in keys
        ]

    return {
        "type": "table",
        "title": title,
        "subtitle": subtitle,
        "columns": columns,
        "rows": [{key: row.get(key, "—") for key in keys} for row in rows],
        }


def breakdown_items(
    rows: list[dict[str, Any]],
    label_key: str,
    pct_key: str,
    value_key: str | None = None,
    ) -> list[dict[str, Any]]:

    """Rows as labelled bars: a label, a percent for the bar, and an amount when there is one."""

    return [
        {
            "label": word(row.get(label_key)),
            "pct": float(row.get(pct_key) or 0),
            "value": money(row.get(value_key)) if value_key else pct(row.get(pct_key)),
            }
        for row in rows
        ]


def holding_row(
    record: Any,
    named: dict[str, Any],
    ) -> dict[str, str]:

    """One holding as a table row: what it is, units, money put in and worth today."""

    return {
        "Name": named.get("name") or "Holding",
        "Units": plain_number(record.units) if record.units is not None else "—",
        "Invested": money(record.invested_amount),
        "Worth today": money(named.get("value_today") if named.get("value_today") is not None else record.current_value),
        }


def record_row(
    kind: RecordKind,
    record: Any,
    ) -> dict[str, str]:

    """One saved item as a table row: its name, its type, then its key facts."""

    described = generic_describe(kind, record)

    row = {"Name": described.name}

    if described.chips:
        row["Type"] = described.chips[0]

    row.update({fact["label"]: fact["value"] for fact in described.facts})

    return row


@never_fails
def records_block(
    kind: RecordKind,
    records: list[Any],
    named: dict[int, dict[str, Any]],
    total: int,
    ) -> Block | None:

    """The user's saved items of one kind as a table, or None when there are none."""

    if not records:
        return None

    if kind == RecordKind.holdings:
        rows = [holding_row(record, named.get(record.id, {})) for record in records]

    else:
        rows = [record_row(kind, record) for record in records]

    title = f"Your {kind.value.replace('_', ' ')}"
    subtitle = f"Showing {len(records)} of {total}" if total > len(records) else None

    return table(title, rows, subtitle)


@never_fails
def goal_progress_block(progress: GoalProgress) -> Block | None:

    """Each active goal with what it needs each month, what is free for it and the shortfall, or None with no goals."""

    if not progress.goals:
        return None

    flow = progress.cash_flow

    goals = [
        {
            "name": goal.name,
            "target_year": goal.target_year,
            "on_track": goal.on_track,
            "target_today": money(goal.target_today),
            "target_future": money(goal.target_future),
            "monthly_need": money(goal.monthly_need),
            "monthly_assigned": money(goal.monthly_assigned),
            "shortfall": money(goal.shortfall),
            "covered_pct": FULL if goal.monthly_need <= 0 else min(goal.monthly_assigned / goal.monthly_need * FULL, FULL),
            }
        for goal in progress.goals
        ]

    return {
        "type": "goal_progress",
        "title": "Goal progress",
        "summary": [
            {"label": "Free each month", "value": money(flow.surplus)},
            {"label": "Free cash, not linked", "value": money(progress.free_cash)},
            ],
        "goals": goals,
        }


@never_fails
def exposure_block(data: dict[str, Any]) -> Block | None:

    """The user's stocks and funds split by asset class and by sector, or None when nothing has a value."""

    if not data.get("holdings_counted"):
        return None

    return {
        "type": "breakdown",
        "title": "Your investment mix",
        "subtitle": f"{money(data['total_value'])} across {data['holdings_counted']} holdings",
        "groups": [
            {"title": "By asset class", "items": breakdown_items(data["by_asset_class"], "asset_class", "pct_of_total", "value")},
            {"title": "By sector", "items": breakdown_items(data["by_sector"][:TOP_SECTORS], "sector", "pct_of_total", "value")},
            ],
        }


def asset_items(split: dict[str, float]) -> list[dict[str, Any]]:

    """A fund's asset split as labelled bars."""

    return [{"label": word(name), "pct": float(weight), "value": pct(weight)} for name, weight in split.items()]


@never_fails
def fund_block(data: dict[str, Any]) -> Block:

    """One fund's plans, top holdings, sector split and asset split, stacked in one card."""

    plan = data["this_plan"]

    facts = {
        "type": "facts",
        "facts": [
            {"label": "Category", "value": word(data.get("sub_category") or data.get("category"))},
            {"label": "Fund house", "value": word(data.get("amc"))},
            {"label": "NAV", "value": price(plan.get("nav"))},
            {"label": "NAV date", "value": word(plan.get("nav_date"))},
            ],
        }

    blocks: list[Block] = [facts]

    plans = [
        {"Plan": f"{word(item['plan'])}, {word(item['option'])}", "NAV": price(item.get("nav")), "ISIN": item["isin"]}
        for item in data.get("all_plans", [])
        ]

    if plans:
        blocks.append(table("Plans", plans))

    if data.get("portfolio_available"):

        holdings = [
            {"Holding": item["name"], "Sector": word(item.get("sector")), "Weight": pct(item.get("weight_pct"))}
            for item in data.get("top_holdings", [])
            ]

        blocks.append(table("Top holdings", holdings, f"Portfolio as on {word(data.get('portfolio_date'))}"))

        blocks.append({
            "type": "breakdown",
            "groups": [
                {"title": "By sector", "items": breakdown_items(data.get("sector_split", [])[:TOP_SECTORS], "sector", "weight_pct")},
                {"title": "By asset class", "items": asset_items(data.get("asset_split_pct", {}))},
                ],
            })

    return {"type": "stack", "title": data["scheme"], "chips": [word(data.get("category"))], "blocks": blocks}


@never_fails
def stock_block(data: dict[str, Any]) -> Block:

    """One stock or ETF with its last price and the funds that hold the most of it."""

    facts = {
        "type": "facts",
        "facts": [
            {"label": "Last close", "value": price(data.get("last_price"))},
            {"label": "Price date", "value": word(data.get("price_date"))},
            {"label": "Sector", "value": word(data.get("sector"))},
            {"label": "Market cap", "value": word(data.get("market_cap"))},
            ],
        }

    blocks: list[Block] = [facts]

    holders = [
        {"Fund": item["scheme"], "Fund house": word(item.get("amc")), "Weight": pct(item.get("weight_pct"))}
        for item in data.get("top_schemes_holding", [])
        ]

    if holders:
        blocks.append(table("Funds that hold it most", holders, f"Held by {data.get('schemes_holding', 0)} fund schemes"))

    chips = [word(data.get("kind")).upper() if data.get("kind") == "etf" else "Stock", data.get("symbol") or ""]

    return {"type": "stack", "title": data["name"], "chips": [chip for chip in chips if chip], "blocks": blocks}


@never_fails
def compare_block(data: dict[str, Any]) -> Block:

    """Two to four funds side by side, how much they overlap, and each one's biggest sectors."""

    funds = [
        {
            "Fund": item["scheme"],
            "Category": word(item.get("sub_category") or item.get("category")),
            "NAV": price(item.get("nav")),
            "Stocks held": str(item.get("equity_holdings", 0)),
            }
        for item in data.get("funds", [])
        ]

    overlap = [
        {"Funds": " vs ".join(pair["funds"]), "Common stocks": str(pair["common_stocks"]), "Overlap": pct(pair["overlap_pct"])}
        for pair in data.get("overlap", [])
        ]

    sectors = {
        "type": "breakdown",
        "groups": [
            {"title": item["scheme"], "items": breakdown_items(item.get("sector_split", [])[:TOP_COMPARE_SECTORS], "sector", "weight_pct")}
            for item in data.get("funds", [])
            if item.get("sector_split")
            ],
        }

    blocks: list[Block] = [table("Funds", funds), table("Overlap", overlap)]

    if sectors["groups"]:
        blocks.append(sectors)

    return {"type": "stack", "title": "Fund comparison", "blocks": blocks}


@never_fails
def search_block(data: dict[str, Any]) -> Block | None:

    """The stocks and fund schemes a search found, as one or two tables, or None when nothing matched."""

    blocks: list[Block] = []

    stocks = [
        {"Name": item["name"], "Symbol": item.get("symbol") or "—", "Type": word(item.get("kind")), "Last close": price(item.get("last_price"))}
        for item in data.get("stocks", [])
        ]

    funds = [
        {
            "Scheme": item["scheme"],
            "Fund house": word(item.get("amc")),
            "Category": word(item.get("sub_category") or item.get("category")),
            "Plans": str(len(item.get("plans", []))),
            }
        for item in data.get("funds", [])
        ]

    if stocks:
        blocks.append(table("Stocks and ETFs", stocks))

    if funds:
        blocks.append(table("Mutual funds", funds))

    if not blocks:
        return None

    if len(blocks) == 1:
        return blocks[0]

    return {"type": "stack", "title": "Search results", "blocks": blocks}


def form_block(
    form: str,
    values: dict[str, Any],
    record_id: int | None,
    ) -> Block:

    """A form for the frontend to open beside the chat, with the values the agent already knows."""

    return {"type": "form", "form": form, "values": values, "record_id": record_id}
