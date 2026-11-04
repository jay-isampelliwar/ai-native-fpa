"""The approval gate: pause before a risky tool call, then run what the user approved and answer the rest as rejected."""

from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.messages import AIMessage, ToolCall, ToolMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command, Send, interrupt

from app.agent.budget import TOOL_CALL_LIMIT, Budget, add_tool_calls, new_budget, over_tool_limit, with_limit
from app.agent.context import PlannerContext
from app.agent.nodes import AGENT_NODE, TOOLS_NODE
from app.agent.state import PlannerState
from app.agent.tools.labels import label_for
from app.agent.tools.policies import needs_approval
from app.agent.tools.records import record_fields, show_value
from app.agent.tools.results import over_limit, rejected, to_message
from app.db.session import SessionLocal
from app.features.investments.service import InvestmentService
from app.features.records.exceptions import RecordError
from app.features.records.kinds import KINDS
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


async def saved_fields(call: ToolCall, user_id: int) -> dict[str, Any] | None:

    """Read the saved item the call points at as readable fields, or None when it is not this user's."""

    kind = call["args"].get("kind")
    record_id = call["args"].get("record_id")

    if kind not in KINDS or record_id is None:
        return None

    try:

        async with SessionLocal() as session:
            record = await RecordService(session).get_or_fail(user_id, kind, record_id)

    except RecordError:
        return None

    return record_fields(record)


async def remove_preview(call: ToolCall, user_id: int) -> Preview | None:

    """Show every saved field of the item a delete would remove."""

    current = await saved_fields(call, user_id)

    if current is None:
        return None

    fields = [{"name": name, "value": value} for name, value in current.items() if name != "id"]

    return {"action": "remove", "title": f"Remove this {KINDS[call['args']['kind']].label}?", "fields": fields}


async def change_preview(call: ToolCall, user_id: int) -> Preview | None:

    """Show each field an update would change as its saved value and its new value."""

    changes = call["args"].get("changes")
    current = await saved_fields(call, user_id)

    if current is None or not isinstance(changes, dict) or not changes:
        return None

    kind = call["args"]["kind"]

    if any(name not in editable_fields(kind) for name in changes):
        return None

    fields = [
        {"name": name, "old": current.get(name, NOT_SET), "new": show_value(value)}
        for name, value in changes.items()
        ]

    return {"action": "change", "title": f"Change this {KINDS[kind].label}?", "fields": fields}


def general_preview(call: ToolCall) -> Preview:

    """Show the call's own arguments, for a tool that needs approval but has no preview of its own."""

    fields = [{"name": name, "value": show_value(value)} for name, value in call["args"].items()]

    return {"action": "run", "title": f"Allow: {label_for(call['name'])}?", "fields": fields}


async def confirm_preview(call: ToolCall, user_id: int) -> Preview | None:

    """Show the units worked out from the amount and today's price, for the user to say correct or fix them."""

    try:

        async with SessionLocal() as session:
            estimate = await InvestmentService(session).estimate(call["args"]["isin"], Decimal(str(call["args"]["amount"])))

    except (RecordError, InvalidOperation):
        return None

    instrument = estimate.instrument
    units = show_value(estimate.units)
    amount = show_value(estimate.amount)

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
        "title": f"Is this correct for {instrument.name}?",
        "fields": fields,
        "editable": {"units": units, "amount": amount},
        "resolved": {"units": units},
        }


PREVIEWS = {"delete_record": remove_preview, "update_record": change_preview, "add_holding": confirm_preview}


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
