"""The approval gate: pause before a risky tool call, then run what the user approved and answer the rest as rejected."""

from typing import Any

from langchain_core.messages import AIMessage, ToolCall, ToolMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command, Send, interrupt

from app.agent.context import PlannerContext
from app.agent.nodes import AGENT_NODE, TOOLS_NODE
from app.agent.state import PlannerState
from app.agent.tools.records import show_value
from app.db.session import SessionLocal
from app.features.records.exceptions import RecordError
from app.features.records.kinds import KINDS
from app.features.records.record_service import SYSTEM_COLUMNS, RecordService


APPROVAL_TOOLS = frozenset({"delete_record"})

APPROVE = "approve"
REJECT = "reject"
CANCEL = "cancel"

REJECTED_FLAG = "approval_rejected"

REJECTED_TEXT = "Not done. The user did not approve this, so nothing was changed."

CANCELLED_TEXT = "Not done. The user stopped this reply, so nothing was changed."


async def preview_for(call: ToolCall, user_id: int) -> dict[str, Any] | None:

    """Describe the exact item the call would change as a title and its filled-in fields, or None when it does not exist."""

    kind = call["args"].get("kind")
    record_id = call["args"].get("record_id")

    if kind not in KINDS or record_id is None:
        return None

    try:

        async with SessionLocal() as session:
            record = await RecordService(session).get_or_fail(user_id, kind, record_id)

    except RecordError:
        return None

    columns = [name for name in record.__table__.columns.keys() if name not in SYSTEM_COLUMNS]

    fields = [
        {"name": name, "value": show_value(getattr(record, name))}
        for name in columns
        if getattr(record, name) is not None
        ]

    return {"title": f"Remove this {KINDS[kind].label}?", "fields": fields}


def approved(call: ToolCall, answer: dict[str, Any]) -> bool:

    """Say yes only when the answer approves this exact call with the exact arguments the user was shown."""

    return (
        answer.get("decision") == APPROVE
        and answer.get("tool_call_id") == call["id"]
        and answer.get("arguments") == call["args"]
        )


def closes_turn(answer: dict[str, Any]) -> bool:

    """Say whether the answer ends the turn, a cancel or a reject that wants no reply, so no further pause is asked."""

    return answer.get("decision") == CANCEL or not answer.get("reply", True)


def rejected_message(call: ToolCall, text: str = REJECTED_TEXT) -> ToolMessage:

    """The tool reply for a call the user did not approve, flagged so the worker saves it as rejected."""

    return ToolMessage(
        text,
        tool_call_id=call["id"],
        name=call["name"],
        status="error",
        additional_kwargs={REJECTED_FLAG: True},
        )


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
            allowed.append(call)

        else:
            refused.append(call)

        if closes_turn(answer):

            refused.extend(calls[index + 1:])

            break

    return allowed, refused, answers


async def approval_gate(state: PlannerState, runtime: Runtime[PlannerContext]) -> Command:

    """Send safe calls straight to the tools, hold risky ones until the user decides each, and skip every call on a cancel."""

    message: AIMessage = state["messages"][-1]
    risky = [call for call in message.tool_calls if call["name"] in APPROVAL_TOOLS]

    if not risky:
        return Command(goto=TOOLS_NODE)

    allowed, refused, answers = await ask_each(risky, runtime.context.user_id)

    if any(answer.get("decision") == CANCEL for answer in answers):

        cancelled = [rejected_message(call, CANCELLED_TEXT) for call in message.tool_calls]

        return Command(goto=END, update={"messages": cancelled, "skip_reply": True})

    reply = all(answer.get("reply", True) for answer in answers)

    update = {"messages": [rejected_message(call) for call in refused], "skip_reply": not reply}

    if not refused:
        return Command(goto=TOOLS_NODE, update=update)

    to_run = [call for call in message.tool_calls if call["name"] not in APPROVAL_TOOLS] + allowed

    if to_run:
        return Command(goto=Send(TOOLS_NODE, to_run), update=update)

    return Command(goto=AGENT_NODE if reply else END, update=update)
