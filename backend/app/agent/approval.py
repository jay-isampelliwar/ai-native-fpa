"""The approval gate: pause before a risky tool call, then run what the user approved and answer the rest as rejected."""

from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.messages import AIMessage, ToolCall, ToolMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command, Send, interrupt
from pydantic import ValidationError
from sqlalchemy import select

from app.agent.budget import TOOL_CALL_LIMIT, Budget, add_tool_calls, new_budget, over_tool_limit, with_limit
from app.agent.cards import (
    Described,
    change_title,
    describe,
    humanize,
    label_of,
    plain_number,
    remove_note,
    remove_title,
    rupees,
    show,
    )
from app.agent.context import PlannerContext
from app.agent.nodes import AGENT_NODE, TOOLS_NODE
from app.agent.state import PlannerState
from app.agent.tools.labels import label_for
from app.agent.tools.policies import needs_approval
from app.agent.tools.records import record_fields, show_value
from app.agent.tools.results import over_limit, rejected, to_message
from app.db.models import Holding, MutualFund, Stock
from app.db.session import SessionLocal
from app.features.investments.service import InvestmentService
from app.features.records.exceptions import RecordError
from app.features.records.kinds import KINDS, RecordKind
from app.features.records.record_service import RecordService, editable_fields


APPROVE = "approve"
REJECT = "reject"
CANCEL = "cancel"

USER_REJECTED = "user_rejected"
RUN_CANCELLED = "run_cancelled"

REJECTED_TEXT = "Not done. The user did not approve this, so nothing was changed."

CANCELLED_TEXT = "Not done. The user stopped this reply, so nothing was changed."


NOT_SET = "not set"

CONFIRM_EDITS = ("units", "amount")

type Preview = dict[str, Any]


async def load_record(
    call: ToolCall,
    user_id: int,
    ) -> tuple[RecordKind, Any, Described, dict[str, Any]] | None:

    """Read the saved item the call points at, how it reads on a card and its raw fields, or None when it is not this user's."""

    kind = call["args"].get("kind")
    record_id = call["args"].get("record_id")

    if kind not in KINDS or record_id is None:
        return None

    try:

        async with SessionLocal() as session:
            record = await RecordService(session).get_or_fail(user_id, kind, record_id)
            described = await describe(session, RecordKind(kind), record)

    except RecordError:
        return None

    return RecordKind(kind), record, described, record_fields(record)


async def remove_preview(call: ToolCall, user_id: int) -> Preview | None:

    """Name the item a delete would remove, with its key facts and a line on what removing does not do."""

    loaded = await load_record(call, user_id)

    if loaded is None:
        return None

    kind, _, described, current = loaded

    return {
        "action": "remove",
        "title": remove_title(described),
        "subtitle": described.summary,
        "chips": described.chips,
        "facts": described.facts,
        "note": {"tone": "warn", "text": remove_note(kind)},
        "fields": [{"name": name, "value": value} for name, value in current.items() if name != "id"],
        }


def real_changes(
    kind: RecordKind,
    record: Any,
    changes: dict[str, Any],
    ) -> dict[str, Any] | None:

    """The asked-for fields whose checked new value differs from the saved one, or None when the change would be refused."""

    allowed = editable_fields(kind)

    if any(name not in allowed for name in changes):
        return None

    current = {name: getattr(record, name) for name in allowed}

    try:
        checked = KINDS[kind].schema(**{**current, **changes})

    except ValidationError:
        return None

    return {name: getattr(checked, name) for name in changes if getattr(checked, name) != current[name]}


async def change_preview(call: ToolCall, user_id: int) -> Preview | None:

    """Name the item an update would change and show only the fields that really change, old next to new."""

    changes = call["args"].get("changes")

    if not isinstance(changes, dict) or not changes:
        return None

    loaded = await load_record(call, user_id)

    if loaded is None:
        return None

    kind, record, described, current = loaded

    if kind == RecordKind.holdings and "isin" in changes:
        return await move_preview(call, user_id, record, described, current)

    if kind == RecordKind.holdings:
        changes = await resolved_amounts(record, changes)

    changed = real_changes(kind, record, changes)

    if not changed:
        return None

    model = type(record)
    unchanged_units = kind == RecordKind.holdings and "units" not in changed
    note = f"Nothing else changes. Your units stay {plain_number(record.units)}." if unchanged_units else "Nothing else changes."

    if kind == RecordKind.holdings and "units" in changed and "units" not in changes:
        note = f"Units worked out at the latest NAV or price: {plain_number(changed['units'])}."

    return {
        "action": "change",
        "title": change_title(kind, described),
        "subtitle": described.summary,
        "chips": described.chips,
        "changes": [
            {"label": label_of(name), "old": show(model, name, getattr(record, name)), "new": show(model, name, value)}
            for name, value in changed.items()
            ],
        "note": {"tone": "calm", "text": note},
        "fields": [
            {"name": name, "old": current.get(name, NOT_SET), "new": show_value(value)}
            for name, value in changed.items()
            ],
        }


INSTRUMENT_COLUMNS = ("asset_type", "stock_id", "mutual_fund_id")


async def resolved_amounts(
    record: Holding,
    changes: dict[str, Any],
    ) -> dict[str, Any]:

    """The holding changes with units worked out from a money change, or the changes as given when that cannot be done."""

    try:

        async with SessionLocal() as session:
            return await InvestmentService(session).amount_changes(record, dict(changes))

    except RecordError:
        return changes


async def plan_name(
    session: Any,
    stock_id: int | None,
    mutual_fund_id: int | None,
    ) -> str:

    """The full name of a fund plan with its plan and option, such as '... - Direct Plan - Growth', or a stock's name."""

    if mutual_fund_id is not None:
        return await session.scalar(select(MutualFund.scheme_name).where(MutualFund.id == mutual_fund_id)) or NOT_SET

    return await session.scalar(select(Stock.company_name).where(Stock.id == stock_id)) or NOT_SET


async def move_preview(
    call: ToolCall,
    user_id: int,
    record: Holding,
    described: Described,
    current: dict[str, Any],
    ) -> Preview | None:

    """Show a holding moving to another stock or fund: old name next to new, then the units, amount and value it will have."""

    try:

        async with SessionLocal() as session:
            resolved = await InvestmentService(session).move_changes(user_id, record, dict(call["args"]["changes"]))
            new_isin = str(call["args"]["changes"]["isin"])
            chips, _ = await instrument_labels(session, new_isin, new_isin)
            old_name = await plan_name(session, record.stock_id, record.mutual_fund_id)
            new_name = await plan_name(session, resolved.get("stock_id"), resolved.get("mutual_fund_id"))

    except RecordError:
        return None

    changed = real_changes(RecordKind.holdings, record, resolved)

    if not changed:
        return None

    moving = any(name in changed for name in INSTRUMENT_COLUMNS)

    rows = [{"label": "Fund or stock", "old": old_name, "new": new_name}] if moving else []

    rows += [
        {"label": label_of(name), "old": show(Holding, name, getattr(record, name)), "new": show(Holding, name, value)}
        for name, value in changed.items()
        if name not in INSTRUMENT_COLUMNS and name != "as_of_date"
        ]

    note = "Today's value is worked out from the new fund's latest price." if moving else "Nothing else changes."

    return {
        "action": "change",
        "title": "Move this holding to another fund?" if moving else change_title(RecordKind.holdings, described),
        "subtitle": described.summary,
        "chips": chips if moving else described.chips,
        "changes": rows,
        "note": {"tone": "warn" if moving else "calm", "text": note},
        "fields": [
            {"name": name, "old": current.get(name, NOT_SET), "new": show_value(value)}
            for name, value in changed.items()
            ],
        }


def general_preview(call: ToolCall) -> Preview:

    """Show the call's own arguments, for a tool that needs approval but has no preview of its own."""

    fields = [{"name": name, "value": show_value(value)} for name, value in call["args"].items()]

    return {"action": "run", "title": f"Allow: {label_for(call['name'])}?", "fields": fields}


async def confirm_preview(call: ToolCall, user_id: int) -> Preview | None:

    """Show the units worked out from the amount and today's price as one sum, for the user to say right or fix them."""

    try:

        async with SessionLocal() as session:
            estimate = await InvestmentService(session).estimate(call["args"]["isin"], Decimal(str(call["args"]["amount"])))
            chips, name = await instrument_labels(session, estimate.instrument.isin, estimate.instrument.name)

    except (RecordError, InvalidOperation):
        return None

    instrument = estimate.instrument
    units = show_value(estimate.units)
    amount = show_value(estimate.amount)
    word = "units" if instrument.price_label == "NAV" else "shares"
    price_date = f" on {show(Holding, 'as_of_date', instrument.price_date)}" if instrument.price_date else ""

    fields = [
        {"name": "name", "value": instrument.name},
        {"name": "isin", "value": instrument.isin},
        {"name": "amount", "value": amount},
        {"name": instrument.price_label, "value": show_value(instrument.price)},
        {"name": "price_date", "value": show_value(instrument.price_date) if instrument.price_date else NOT_SET},
        {"name": "units", "value": units},
        ]

    return {
        "action": "confirm",
        "title": "Is this right?",
        "subtitle": name,
        "chips": chips,
        "summary": {
            "lead": f"You put in {rupees(estimate.amount)}, so you have about",
            "big": f"{plain_number(estimate.units)} {word}",
            "how": f"{rupees(estimate.amount)} ÷ {rupees(instrument.price, 2)} per {word[:-1]} (price{price_date})",
            },
        "note": {"tone": "calm", "text": f"Your statement shows the exact {word}. If it is different, tap \"No, let me fix it\"."},
        "fields": fields,
        "editable": {"units": units, "amount": amount},
        "resolved": {"units": units},
        }


async def deposit_preview(call: ToolCall, user_id: int) -> Preview:

    """Ask the user to say a deposit is really a bank deposit, when its bank also runs mutual funds."""

    bank = str(call["args"].get("bank_name", ""))
    fields = [{"name": name, "value": show_value(value)} for name, value in call["args"].items()]
    facts = []

    if call["args"].get("principal") is not None:
        facts.append({"label": "Amount", "value": rupees(Decimal(str(call["args"]["principal"])))})

    if call["args"].get("interest_rate") is not None:
        facts.append({"label": "Interest", "value": f"{show_value(call['args']['interest_rate'])}% a year"})

    return {
        "action": "confirm",
        "title": "Is this a bank fixed deposit?",
        "subtitle": bank,
        "chips": ["Fixed deposit"],
        "facts": facts,
        "note": {
            "tone": "warn",
            "text": f"{bank} also runs mutual funds. Approve only if this is a fixed deposit in the bank. "
            "If it is a mutual fund, reject and say so.",
            },
        "fields": fields,
        }


async def instrument_labels(
    session: Any,
    isin: str,
    fallback: str,
    ) -> tuple[list[str], str]:

    """The labels and short name of a fund plan or stock, such as Mutual fund, Direct plan, Growth."""

    fund = await session.scalar(select(MutualFund).where(MutualFund.isin == isin))

    if fund is not None:
        return ["Mutual fund", f"{humanize(fund.plan_type.value)} plan", humanize(fund.option_type.value)], fund.base_scheme_name or fund.scheme_name

    stock = await session.scalar(select(Stock).where(Stock.isin == isin))

    if stock is not None:
        return ["ETF" if stock.is_etf else "Stock", stock.symbol], stock.company_name

    return [], fallback


PREVIEWS = {
    "delete_record": remove_preview,
    "update_record": change_preview,
    "add_stock_or_fund": confirm_preview,
    "add_fixed_deposit": deposit_preview,
    }


async def preview_for(call: ToolCall, user_id: int) -> Preview | None:

    """Describe exactly what the call would do, or None when it points at nothing and the tool can refuse it alone."""

    build = PREVIEWS.get(call["name"])

    if build is None:
        return general_preview(call)

    return await build(call, user_id)


def approved(call: ToolCall, answer: dict[str, Any]) -> bool:

    """Say yes only when the answer approves this exact call with the exact arguments the user was shown."""

    return (
        answer.get("decision") == APPROVE
        and answer.get("tool_call_id") == call["id"]
        and answer.get("arguments") == call["args"]
        )


def checked_edits(
    preview: Preview,
    answer: dict[str, Any],
    ) -> dict[str, str]:

    """Keep only the edits this card allows, each a number not below zero, written as plain text."""

    allowed = preview.get("editable") or {}
    edits = answer.get("edits") or {}
    kept = {}

    for name, value in edits.items():

        if name not in allowed or name not in CONFIRM_EDITS:
            continue

        try:
            number = Decimal(str(value))

        except InvalidOperation:
            continue

        if number.is_finite() and number >= 0:
            kept[name] = format(number.normalize(), "f")

    return kept


def final_call(
    call: ToolCall,
    preview: Preview,
    answer: dict[str, Any],
    ) -> ToolCall:

    """The call to run once approved: with the values the user fixed, else with the values the card showed."""

    edits = checked_edits(preview, answer)
    resolved = preview.get("resolved") or {}

    if not edits and not resolved:
        return call

    return {**call, "args": {**call["args"], **resolved, **edits}}


def closes_turn(answer: dict[str, Any]) -> bool:

    """Say whether the answer ends the turn, a cancel or a reject that wants no reply, so no further pause is asked."""

    return answer.get("decision") == CANCEL or not answer.get("reply", True)


def rejected_message(
    call: ToolCall,
    error_code: str = USER_REJECTED,
    text: str = REJECTED_TEXT,
    ) -> ToolMessage:

    """The tool reply for a call that never ran, as a rejected result so the worker saves it as rejected."""

    return to_message(rejected(error_code, text), call["id"], call["name"])


async def ask_each(
    calls: list[ToolCall],
    user_id: int,
    ) -> tuple[list[ToolCall], list[ToolCall], list[dict[str, Any]]]:

    """Pause once per risky call, and split them into approved and rejected, refusing the rest once an answer closes the turn."""

    allowed = []
    refused = []
    answers = []

    for index, call in enumerate(calls):

        preview = await preview_for(call, user_id)

        if preview is None:

            allowed.append(call)

            continue

        answer = interrupt({"tool_call_id": call["id"], "name": call["name"], "args": call["args"], "preview": preview})

        answers.append(answer)

        if approved(call, answer):
            allowed.append(final_call(call, preview, answer))

        else:
            refused.append(call)

        if closes_turn(answer):

            refused.extend(calls[index + 1:])

            break

    return allowed, refused, answers


async def approval_gate(state: PlannerState, runtime: Runtime[PlannerContext]) -> Command:

    """Refuse a batch past the tool limit, send safe calls to the tools, hold risky ones for the user, and skip all on a cancel."""

    message: AIMessage = state["messages"][-1]
    budget: Budget = state.get("budget") or new_budget()

    if over_tool_limit(budget, len(message.tool_calls)):

        refused = [to_message(over_limit(TOOL_CALL_LIMIT), call["id"], call["name"]) for call in message.tool_calls]

        return Command(goto=AGENT_NODE, update={"messages": refused, "budget": with_limit(budget, TOOL_CALL_LIMIT)})

    budget = add_tool_calls(budget, len(message.tool_calls))
    risky = [call for call in message.tool_calls if needs_approval(call["name"], call["args"])]

    if not risky:
        return Command(goto=TOOLS_NODE, update={"budget": budget})

    allowed, refused, answers = await ask_each(risky, runtime.context.user_id)

    if any(answer.get("decision") == CANCEL for answer in answers):

        cancelled = [rejected_message(call, RUN_CANCELLED, CANCELLED_TEXT) for call in message.tool_calls]

        return Command(goto=END, update={"messages": cancelled, "skip_reply": True, "budget": budget})

    reply = all(answer.get("reply", True) for answer in answers)

    update = {"messages": [rejected_message(call) for call in refused], "skip_reply": not reply, "budget": budget}

    changed = any(call not in message.tool_calls for call in allowed)

    if not refused and not changed:
        return Command(goto=TOOLS_NODE, update=update)

    to_run = [call for call in message.tool_calls if not needs_approval(call["name"], call["args"])] + allowed

    if to_run:
        return Command(goto=Send(TOOLS_NODE, to_run), update=update)

    return Command(goto=AGENT_NODE if reply else END, update=update)
