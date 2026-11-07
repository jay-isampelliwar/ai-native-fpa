"""Typed UI blocks built in code from exact tool data, so the chat can draw a card instead of a markdown table."""

import functools
import logging
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from app.agent.cards import Described, generic_describe, humanize, label_of, plain_number, rupees
from app.db.models.base import UserOwnedMixin
from app.features.analysis.service import GoalProgress
from app.features.indices.schemas import IndexQuote
from app.features.indices.service import IST
from app.features.overview.service import Event, Health, MonthSummary, NetWorth
from app.features.records.kinds import KINDS, RecordKind


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


def short_name(name: str) -> str:

    """A fund or company name without its plan and option, in normal case, such as 'Bandhan Small Cap Fund'."""

    head = name.split(" - ")[0].strip()

    for ending in (" Limited", " Ltd.", " Ltd"):
        head = head.removesuffix(ending)

    return head.title() if head.isupper() else head


def signed_money(value: Decimal) -> str:

    """A rupee change with its sign, such as +₹1,200 or −₹1,764.46."""

    return f"{'+' if value >= 0 else '−'}{rupees(abs(value), 2)}"


def holding_value(
    record: Any,
    named: dict[str, Any],
    ) -> Decimal | None:

    """What a holding is worth now: from the latest NAV or price when known, else its saved current value."""

    value = named.get("value_today")

    if value is None:
        value = record.current_value

    return None if value is None else Decimal(str(value))


def holdings_block(
    records: list[Any],
    named: dict[int, dict[str, Any]],
    total: int,
    ) -> Block | None:

    """The holdings card: total value and overall gain, then each holding by size with its share of the money."""

    rows = []

    for record in records:

        about = named.get(record.id, {})

        rows.append((record, about, holding_value(record, about)))

    rows.sort(key=lambda row: row[2] if row[2] is not None else Decimal(-1), reverse=True)

    worth = sum((value for _, _, value in rows if value is not None), Decimal(0))

    invested = sum(
        (Decimal(str(record.invested_amount)) for record, _, value in rows if value is not None and record.invested_amount is not None),
        Decimal(0),
        )

    gained = sum(
        (value for record, _, value in rows if value is not None and record.invested_amount is not None),
        Decimal(0),
        ) - invested

    summary: list[dict[str, Any]] = [{"label": "Value", "value": rupees(worth, 2)}]

    if invested:

        summary.append({
            "label": "Overall",
            "value": signed_money(gained),
            "note": f"{'+' if gained >= 0 else '−'}{abs(gained) / invested * 100:.2f}%",
            "direction": "up" if gained >= 0 else "down",
            })

    dates = [about.get("nav_date") or about.get("price_date") for _, about, _ in rows]
    known = [day for day in dates if day is not None]

    items = [
        {
            "name": short_name(about.get("name") or "Holding"),
            "value": rupees(value, 2) if value is not None else "—",
            "share": round(float(value / worth * 100), 2) if value is not None and worth else 0.0,
            }
        for _, about, value in rows
        ]

    return {
        "type": "holdings",
        "title": "Your holdings",
        "as_of": word(min(known)) if known else None,
        "subtitle": f"Showing {len(records)} of {total}" if total > len(records) else None,
        "summary": summary,
        "items": items,
        }


@never_fails
def records_block(
    kind: RecordKind,
    records: list[Any],
    named: dict[int, dict[str, Any]],
    total: int,
    ) -> Block | None:

    """The user's saved items of one kind as a table, or an empty card with the form that adds one when there are none."""

    if not records:
        return empty_block(kind)

    if kind == RecordKind.holdings:
        return holdings_block(records, named, total)

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


def short_scheme(name: str) -> str:

    """A scheme name without its plan and option words, such as 'HDFC Flexi Cap Fund'."""

    return name.split(" - ")[0].strip()


def top_sector(item: dict[str, Any]) -> str:

    """The biggest sector in a fund's portfolio, or a dash when its portfolio is not loaded."""

    sectors = item.get("sector_split") or []

    return word(sectors[0].get("sector")) if sectors else "—"


@never_fails
def compare_block(data: dict[str, Any]) -> Block:

    """Two to four funds side by side, one row per measure, with how much they overlap as the note."""

    funds = data.get("funds", [])

    def split(
        item: dict[str, Any],
        part: str,
        ) -> str:

        """One part of a fund's asset split as a percent, or a dash."""

        value = (item.get("asset_split_pct") or {}).get(part)

        return pct(value) if value is not None else "—"

    rows = [
        {"label": "Category", "values": [word(item.get("sub_category") or item.get("category")) for item in funds], "best": None},
        {"label": "NAV", "values": [price(item.get("nav")) for item in funds], "best": None},
        {"label": "Stocks held", "values": [str(item.get("equity_holdings", 0)) for item in funds], "best": None},
        {"label": "Equity", "values": [split(item, "equity") for item in funds], "best": None},
        {"label": "Debt", "values": [split(item, "debt") for item in funds], "best": None},
        {"label": "Top sector", "values": [top_sector(item) for item in funds], "best": None},
        ]

    overlaps = [
        f"{' vs '.join(pair['funds'])}: {pair['common_stocks']} stocks in common, {pct(pair['overlap_pct'])} overlap"
        for pair in data.get("overlap", [])
        ]

    return {
        "type": "compare",
        "title": "Fund comparison",
        "columns": [short_scheme(item["scheme"]) for item in funds],
        "rows": rows,
        "note": "; ".join(overlaps) or None,
        }


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


@never_fails
def sources_block(data: dict[str, Any]) -> Block | None:

    """The web pages a search found, as titled links with their site and date, or None when it found none."""

    items = [
        {
            "title": item["title"],
            "url": item["url"],
            "site": item["site"],
            "published": item.get("published"),
            "image": item.get("image"),
            }
        for item in data.get("results", [])
        ]

    if not items:
        return None

    return {"type": "sources", "title": "Sources", "items": items}


def index_number(value: float) -> str:

    """An index level or change with Indian commas and two decimals, such as 25,030.35, without its sign."""

    text = rupees(Decimal(f"{abs(value):.2f}"), 2).removeprefix("₹")

    return text if "." in text else f"{text}.00"


def ist_time(timestamp: int) -> str:

    """A Unix time as a short IST time, such as 6 Nov, 3:31 pm IST."""

    moment = datetime.fromtimestamp(timestamp, IST)

    return f"{moment.day} {moment:%b}, {moment:%-I:%M} {moment:%p}".replace("AM", "am").replace("PM", "pm") + " IST"


def quote_item(
    quote: IndexQuote,
    with_stats: bool,
    ) -> dict[str, Any]:

    """One index's level and change for the quote card, with open, high, low and previous close when asked."""

    change = quote.value - quote.previous_close

    item: dict[str, Any] = {
        "name": quote.name,
        "value": index_number(quote.value),
        "number": round(quote.value, 2),
        "change": f"{'+' if change >= 0 else '-'}{index_number(change)}",
        "change_pct": f"{abs(change) / quote.previous_close * 100:.2f}%",
        "direction": "up" if change >= 0 else "down",
        }

    if with_stats:

        item["stats"] = [
            {"label": label, "value": index_number(value) if value is not None else "—"}
            for label, value in (
                ("Open", quote.open),
                ("High", quote.high),
                ("Low", quote.low),
                ("Prev close", quote.previous_close),
                )
            ]

    return item


@never_fails
def quote_block(
    quotes: list[IndexQuote],
    market_open: bool,
    ) -> Block | None:

    """The quote card: one index with its four stats, or several indices with only their level and change, or None when there are none."""

    if not quotes:
        return None

    return {
        "type": "quote",
        "as_of": ist_time(max(quote.as_of for quote in quotes)),
        "closed": not market_open,
        "items": [quote_item(quote, len(quotes) == 1) for quote in quotes],
        }


FORM_FOR_KIND: dict[RecordKind, str] = {
    RecordKind.goals: "goal",
    RecordKind.income: "income",
    RecordKind.expenses: "expense",
    RecordKind.holdings: "holding",
    RecordKind.loans: "loan",
    RecordKind.insurance: "insurance",
    }

SECTION_LABELS = {
    "profile": "Your details",
    "family": "Family",
    "income": "Income",
    "expenses": "Expenses",
    "bank_accounts": "Bank accounts",
    "fixed_deposits": "Fixed deposits",
    "retirement_accounts": "EPF, PPF & NPS",
    "physical_assets": "Property & assets",
    "holdings": "Stocks & funds",
    "loans": "Loans",
    "credit_cards": "Credit cards",
    "insurance": "Insurance",
    "goals": "Goals",
    "tax_profile": "Tax details",
    }

CHECK_STATUS = {"provided": "done", "none": "done", "declined": "declined", "pending": "missing"}


def kind_words(kind: RecordKind) -> str:

    """A record kind as plain words, such as 'bank accounts'."""

    return kind.value.replace("_", " ")


def kind_of(record: UserOwnedMixin) -> RecordKind | None:

    """The record kind whose table this row belongs to, or None for a row with no kind."""

    return next((kind for kind, info in KINDS.items() if info.model is type(record)), None)


def signed(value: Decimal) -> str:

    """A rupee amount with its sign, such as +₹52,400 or −₹1,764."""

    return f"{'+' if value >= 0 else '−'}{rupees(abs(value))}"


def direction(value: Decimal | float | int) -> str:

    """up for zero or more, else down."""

    return "up" if value >= 0 else "down"


def pct_text(value: float) -> str:

    """A percent for a change note, such as 2.9%."""

    return f"{abs(value):.1f}%"


def empty_block(kind: RecordKind) -> Block:

    """The empty card for a kind with nothing saved, with its form when the frontend has one."""

    words = kind_words(kind)

    return {
        "type": "empty",
        "title": f"No {words} saved yet",
        "text": f"Tell me about your {words} in the chat, or open the form.",
        "form": FORM_FOR_KIND.get(kind),
        }


@never_fails
def receipt_block(
    action: str,
    record: UserOwnedMixin,
    name: str | None = None,
    ) -> Block | None:

    """A receipt for a row just saved or removed: its kind in words, its name and its key facts."""

    kind = kind_of(record)

    if kind is None:
        return None

    described = generic_describe(kind, record)

    return {
        "type": "receipt",
        "action": action,
        "kind": KINDS[kind].label.capitalize(),
        "name": name or described.name,
        "record_id": getattr(record, "id", None),
        "facts": described.facts,
        }


def plain_receipt(
    action: str,
    kind: str,
    name: str,
    facts: dict[str, str],
    record_id: int | None = None,
    ) -> Block:

    """A receipt built from plain values, for saves that are not one record row, such as the profile."""

    return {
        "type": "receipt",
        "action": action,
        "kind": kind,
        "name": name,
        "record_id": record_id,
        "facts": [{"label": label_of(label), "value": value} for label, value in facts.items()],
        }


def changes_block(
    described: Described,
    before: dict[str, str],
    after: dict[str, str],
    changed_on: date,
    ) -> Block:

    """The fields an update changed, old beside new, for the item by name."""

    fields = [{"label": label_of(name), "old": before.get(name, "—"), "new": value} for name, value in after.items()]

    return {
        "type": "changes",
        "title": f"Updated · {described.name}",
        "fields": fields,
        "note": f"{len(fields)} {'field' if len(fields) == 1 else 'fields'} changed · {word(changed_on)}",
        }


def checklist_block(statuses: dict[str, str]) -> Block:

    """Every section with whether it is done, still missing or declined, in the order the planner asks."""

    items = [
        {"label": SECTION_LABELS.get(section, humanize(section)), "status": CHECK_STATUS.get(status, "missing")}
        for section, status in statuses.items()
        ]

    done = sum(1 for item in items if item["status"] == "done")

    return {
        "type": "checklist",
        "title": "What I know about you",
        "subtitle": f"{done} of {len(items)} done",
        "items": items,
        }


@never_fails
def net_worth_block(
    worth: NetWorth,
    as_of: date,
    ) -> Block:

    """Net worth as one big number with what is owned, owed, invested and in the bank under it."""

    return {
        "type": "hero",
        "title": "Net worth",
        "as_of": word(as_of),
        "value": signed(worth.value) if worth.value < 0 else rupees(worth.value),
        "change": None,
        "change_note": None,
        "facts": [
            {"label": "Assets", "value": rupees(worth.assets)},
            {"label": "Loans & dues", "value": rupees(worth.owed)},
            {"label": "Invested", "value": rupees(worth.invested)},
            {"label": "In the bank", "value": rupees(worth.cash)},
            ],
        "tone": direction(worth.value),
        }


@never_fails
def asset_split_block(worth: NetWorth) -> Block | None:

    """How what the user owns splits by type, as a ring, or None when nothing is saved."""

    total = worth.assets

    if total <= 0:
        return None

    return {
        "type": "ring",
        "title": "Where your money is",
        "subtitle": f"{len(worth.split)} types of assets",
        "total": rupees(total),
        "items": [
            {"label": label, "value": rupees(value), "pct": round(float(value / total * 100), 2)}
            for label, value in worth.split
            ],
        }


def change_between(
    latest: Decimal,
    previous: Decimal,
    ) -> dict[str, Any] | None:

    """The move from last month to this one as a signed amount and percent, or None when last month was zero."""

    if previous == 0:
        return None

    delta = latest - previous

    return {"text": f"{signed(delta)} ({pct_text(float(delta / previous * 100))})", "direction": direction(delta)}


@never_fails
def month_summary_block(
    summary: MonthSummary,
    as_of: date,
    ) -> Block:

    """Income, spending and what is left this month as three tiles, with a trend and change when transactions exist."""

    history = summary.history

    def tile(
        label: str,
        value: int,
        series: list[Decimal],
        ) -> dict[str, Any]:

        """One tile, with its change and trend only when there is history."""

        item: dict[str, Any] = {"label": label, "value": rupees(Decimal(value))}

        if len(series) >= 2:
            item["change"] = change_between(series[-1], series[-2])
            item["trend"] = [float(point) for point in series]

        return item

    return {
        "type": "kpis",
        "title": "This month",
        "as_of": f"{as_of:%B %Y}",
        "items": [
            tile("Income", summary.income, [flow.income for flow in history]),
            tile("Spending", summary.spending, [flow.spending for flow in history]),
            tile("Saved", summary.saved, [flow.saved for flow in history]),
            ],
        }


@never_fails
def cash_flow_block(summary: MonthSummary) -> Block | None:

    """Income against spending for each of the last six months as grouped bars, or None with no transactions."""

    if not summary.history:
        return None

    return {
        "type": "bars",
        "title": "Income vs spending",
        "subtitle": f"Last {len(summary.history)} months, from your transactions",
        "labels": [f"{flow.month:%b}" for flow in summary.history],
        "series": [
            {"name": "Income", "values": [float(flow.income) for flow in summary.history]},
            {"name": "Spending", "values": [float(flow.spending) for flow in summary.history]},
            ],
        }


@never_fails
def health_block(
    health: Health,
    as_of: date,
    ) -> Block:

    """The health score on a gauge with the four checks behind it."""

    return {
        "type": "gauge",
        "title": "Financial health",
        "as_of": word(as_of),
        "score": health.score,
        "verdict": health.verdict,
        "checks": [{"label": check.label, "value": check.value, "tone": check.tone} for check in health.checks],
        }


@never_fails
def timeline_block(events: list[Event]) -> Block | None:

    """What is coming up as a dated list, or None when nothing is due."""

    if not events:
        return None

    return {
        "type": "timeline",
        "title": "Coming up",
        "items": [
            {"when": event.when, "label": event.label, "value": rupees(event.value) if event.value is not None else None, "state": event.state}
            for event in events
            ],
        }


def form_block(
    form: str,
    values: dict[str, Any],
    record_id: int | None,
    ) -> Block:

    """A form for the frontend to open beside the chat, with the values the agent already knows."""

    return {"type": "form", "form": form, "values": values, "record_id": record_id}
