"""Tests for the confirm card on add_stock_or_fund: correct runs with the shown units, fixed values run with the user's numbers."""

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from app.agent import approval
from app.agent.approval import APPROVE, REJECT, approval_gate, checked_edits
from app.agent.context import PlannerContext
from app.agent.graph import after_tools
from app.agent.nodes import AGENT_NODE, APPROVAL_NODE, TOOLS_NODE
from app.agent.state import PlannerState


AMOUNT_ARGS = {"isin": "INF879O01027", "amount": 50000}

UNITS_ARGS = {"isin": "INF879O01027", "units": 100}

PREVIEW = {
    "action": "confirm",
    "title": "Is this correct for Parag Parikh Flexi Cap Fund?",
    "fields": [{"name": "units", "value": "551.248"}],
    "editable": {"units": "551.248", "amount": "50000"},
    "resolved": {"units": "551.248"},
    }

ran: list[dict[str, Any]] = []


@tool
def add_stock_or_fund(
    isin: str,
    units: int | float | str | None = None,
    amount: int | float | str | None = None,
    ) -> str:

    """Pretend to save a holding, writing numbers as text so tests compare one way."""

    ran.append({"isin": isin, "units": None if units is None else str(units), "amount": None if amount is None else str(amount)})

    return "saved"


def build(args: dict[str, Any]):

    """An agent that asks for one add_stock_or_fund call, the real gate, and a fake tool."""

    def agent(state: PlannerState) -> dict:

        """Ask for the call once, then answer."""

        if isinstance(state["messages"][-1], HumanMessage):
            return {"messages": [AIMessage("", tool_calls=[{"name": "add_stock_or_fund", "args": args, "id": "hold"}])]}

        return {"messages": [AIMessage("done")]}

    def route(state: PlannerState) -> str:

        """Send tool requests to the gate, and end on a plain answer."""

        return APPROVAL_NODE if state["messages"][-1].tool_calls else END

    builder = StateGraph(PlannerState, context_schema=PlannerContext)

    builder.add_node(AGENT_NODE, agent)
    builder.add_node(APPROVAL_NODE, approval_gate, destinations=(TOOLS_NODE, AGENT_NODE, END))
    builder.add_node(TOOLS_NODE, ToolNode([add_stock_or_fund]))

    builder.add_edge(START, AGENT_NODE)
    builder.add_conditional_edges(AGENT_NODE, route, [APPROVAL_NODE, END])
    builder.add_conditional_edges(TOOLS_NODE, after_tools, [AGENT_NODE, END])

    return builder.compile(checkpointer=InMemorySaver())


@pytest.fixture(autouse=True)
def fake_preview(monkeypatch: pytest.MonkeyPatch) -> None:

    """Show a fixed confirm card without the database, and clear the record of saves."""

    async def preview(call: dict[str, Any], user_id: int) -> dict[str, Any]:

        """The same confirm card for any call."""

        return PREVIEW

    monkeypatch.setattr(approval, "preview_for", preview)

    ran.clear()


async def run_until_pause(args: dict[str, Any]):

    """Run to the first pause, or to the end when nothing pauses, and return the graph, config, context and result."""

    graph = build(args)
    config = {"configurable": {"thread_id": "confirm"}}
    context = PlannerContext(user_id=1)

    result = await graph.ainvoke({"messages": [HumanMessage("I put 50k in PPFAS")]}, config, context=context)

    return graph, config, context, result


def resume(
    decision: str,
    edits: dict[str, Any] | None = None,
    ) -> Command:

    """The resume value the approvals service sends after a click."""

    return Command(
        resume={
            "decision": decision,
            "tool_call_id": "hold",
            "arguments": AMOUNT_ARGS,
            "reply": True,
            "edits": edits or {},
            }
        )


async def test_given_units_save_without_a_card() -> None:

    """With units given, the holding is saved at once and nothing pauses."""

    _, _, _, result = await run_until_pause(UNITS_ARGS)

    assert "__interrupt__" not in result
    assert ran == [{"isin": "INF879O01027", "units": "100", "amount": None}]


async def test_amount_only_pauses_on_a_confirm_card() -> None:

    """With only an amount, the run pauses on the confirm card and nothing is saved yet."""

    _, _, _, result = await run_until_pause(AMOUNT_ARGS)

    request = result["__interrupt__"][0].value

    assert request["preview"]["action"] == "confirm"
    assert ran == []


async def test_correct_saves_the_units_the_card_showed() -> None:

    """Clicking correct saves the holding with the units shown on the card, not units worked out again."""

    graph, config, context, _ = await run_until_pause(AMOUNT_ARGS)

    result = await graph.ainvoke(resume(APPROVE), config, context=context)

    assert ran == [{"isin": "INF879O01027", "units": "551.248", "amount": "50000"}]
    assert result["messages"][-1].content == "done"


async def test_fixed_values_save_what_the_user_typed() -> None:

    """Fixed units and amount from the correction box replace the shown ones."""

    graph, config, context, _ = await run_until_pause(AMOUNT_ARGS)

    await graph.ainvoke(resume(APPROVE, {"units": "560.5", "amount": "51000"}), config, context=context)

    assert ran == [{"isin": "INF879O01027", "units": "560.5", "amount": "51000"}]


async def test_not_correct_without_values_saves_nothing() -> None:

    """A reject saves nothing and answers the call as rejected."""

    graph, config, context, _ = await run_until_pause(AMOUNT_ARGS)

    result = await graph.ainvoke(resume(REJECT), config, context=context)

    answers = [message for message in result["messages"] if isinstance(message, ToolMessage)]

    assert ran == []
    assert answers[0].artifact["status"] == "rejected"


def test_edits_keep_only_allowed_numbers() -> None:

    """Only units and amount the card allows survive, as plain numbers, and bad or negative values are dropped."""

    edits = checked_edits(PREVIEW, {"edits": {"units": "12.50", "amount": "-5", "isin": "X", "folio": "1"}})

    assert edits == {"units": "12.5"}
    assert checked_edits(PREVIEW, {"edits": {"units": "abc"}}) == {}
    assert checked_edits({"editable": {}}, {"edits": {"units": "1"}}) == {}
