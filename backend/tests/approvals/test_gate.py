"""Tests for the approval gate on a small in-memory graph with fake tools, so no database or model is needed."""

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from app.agent import approval
from app.agent.approval import APPROVE, CANCEL, REJECT, approval_gate
from app.agent.context import PlannerContext
from app.agent.graph import after_tools
from app.agent.nodes import AGENT_NODE, APPROVAL_NODE, TOOLS_NODE
from app.agent.state import PlannerState


LOAN_ARGS = {"kind": "loans", "record_id": 42}

CAR_ARGS = {"kind": "loans", "record_id": 7}

ran: list[str] = []


@tool
def add_expense(name: str) -> str:

    """Pretend to save an expense."""

    ran.append(f"add_expense:{name}")

    return "added"


@tool
def delete_record(kind: str, record_id: int) -> str:

    """Pretend to remove a saved item."""

    ran.append(f"delete_record:{record_id}")

    return "deleted"


def scripted_agent(calls: list[dict[str, Any]]):

    """An agent node that asks for the given calls on the user's message and answers "done" after tools."""

    def agent(state: PlannerState) -> dict:

        """Ask for the calls once, then answer."""

        if isinstance(state["messages"][-1], HumanMessage):
            return {"messages": [AIMessage("", tool_calls=calls)]}

        return {"messages": [AIMessage("done")]}

    return agent


def route(state: PlannerState) -> str:

    """Send tool requests to the gate, and end on a plain answer."""

    if state["messages"][-1].tool_calls:
        return APPROVAL_NODE

    return END


def build(calls: list[dict[str, Any]]):

    """The planner's agent, gate and tools loop, with a scripted agent and fake tools."""

    builder = StateGraph(PlannerState, context_schema=PlannerContext)

    builder.add_node(AGENT_NODE, scripted_agent(calls))
    builder.add_node(APPROVAL_NODE, approval_gate, destinations=(TOOLS_NODE, AGENT_NODE, END))
    builder.add_node(TOOLS_NODE, ToolNode([add_expense, delete_record]))

    builder.add_edge(START, AGENT_NODE)
    builder.add_conditional_edges(AGENT_NODE, route, [APPROVAL_NODE, END])
    builder.add_conditional_edges(TOOLS_NODE, after_tools, [AGENT_NODE, END])

    return builder.compile(checkpointer=InMemorySaver())


def call(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:

    """One tool call as the model would ask for it."""

    return {"name": name, "args": args, "id": call_id}


def answer(
    decision: str,
    call_id: str = "del",
    arguments: dict[str, Any] = LOAN_ARGS,
    reply: bool = True,
    ) -> dict:

    """The resume value the approvals service sends back to the gate."""

    return {"decision": decision, "tool_call_id": call_id, "arguments": arguments, "reply": reply}


@pytest.fixture(autouse=True)
def fake_preview(monkeypatch: pytest.MonkeyPatch) -> None:

    """Describe every item without the database, and clear the record of tools that ran."""

    async def preview(call: dict[str, Any], user_id: int) -> dict[str, Any]:

        """A fixed preview for any call."""

        return {"title": "Remove this loan?", "fields": [{"name": "record_id", "value": str(call["args"]["record_id"])}]}

    monkeypatch.setattr(approval, "preview_for", preview)

    ran.clear()


async def pause(calls: list[dict[str, Any]]) -> tuple[Any, dict, PlannerContext, Any]:

    """Run the graph to its first pause, and return the graph, config, context and the pause's value."""

    graph = build(calls)
    config = {"configurable": {"thread_id": "test"}}
    context = PlannerContext(user_id=1)

    result = await graph.ainvoke({"messages": [HumanMessage("hi")]}, config, context=context)

    return graph, config, context, result["__interrupt__"][0].value


MIXED = [call("add_expense", {"name": "rent"}, "add"), call("delete_record", LOAN_ARGS, "del")]


async def test_safe_calls_skip_the_gate() -> None:

    """A turn with no risky call runs its tools at once and never pauses."""

    graph = build([call("add_expense", {"name": "rent"}, "add")])

    result = await graph.ainvoke(
        {"messages": [HumanMessage("hi")]},
        {"configurable": {"thread_id": "test"}},
        context=PlannerContext(user_id=1),
        )

    assert "__interrupt__" not in result
    assert ran == ["add_expense:rent"]


async def test_pause_carries_the_call_and_its_preview() -> None:

    """The pause names the risky call, its exact arguments and the preview, and nothing has run yet."""

    _, _, _, request = await pause(MIXED)

    assert request["tool_call_id"] == "del"
    assert request["name"] == "delete_record"
    assert request["args"] == LOAN_ARGS
    assert request["preview"]["title"] == "Remove this loan?"
    assert ran == []


async def test_approve_runs_every_call_and_replies() -> None:

    """An approval runs the safe and the risky call, then the agent answers."""

    graph, config, context, _ = await pause(MIXED)

    result = await graph.ainvoke(Command(resume=answer(APPROVE)), config, context=context)

    assert sorted(ran) == ["add_expense:rent", "delete_record:42"]
    assert result["messages"][-1].content == "done"


async def test_reject_runs_only_the_safe_call() -> None:

    """A reject runs the safe call, answers the risky one as rejected, and the agent still replies."""

    graph, config, context, _ = await pause(MIXED)

    result = await graph.ainvoke(Command(resume=answer(REJECT)), config, context=context)

    rejected = [message for message in result["messages"] if isinstance(message, ToolMessage) and message.tool_call_id == "del"]

    assert ran == ["add_expense:rent"]
    assert rejected[0].additional_kwargs[approval.REJECTED_FLAG] is True
    assert result["messages"][-1].content == "done"


async def test_approval_with_changed_arguments_is_a_reject() -> None:

    """An approval for different arguments than the paused call does not run the risky call."""

    graph, config, context, _ = await pause(MIXED)

    await graph.ainvoke(Command(resume=answer(APPROVE, arguments=CAR_ARGS)), config, context=context)

    assert ran == ["add_expense:rent"]


async def test_reject_without_reply_ends_after_tools() -> None:

    """A reject that wants no reply, as from a new message or expiry, runs safe calls and stops without the agent."""

    graph, config, context, _ = await pause(MIXED)

    result = await graph.ainvoke(Command(resume=answer(REJECT, reply=False)), config, context=context)

    assert ran == ["add_expense:rent"]
    assert isinstance(result["messages"][-1], ToolMessage)


async def test_cancel_runs_nothing() -> None:

    """A cancel answers every call, safe ones too, as not done and ends the turn."""

    graph, config, context, _ = await pause(MIXED)

    result = await graph.ainvoke(Command(resume=answer(CANCEL, reply=False)), config, context=context)

    answered = {message.tool_call_id for message in result["messages"] if isinstance(message, ToolMessage)}

    assert ran == []
    assert answered == {"add", "del"}


async def test_closing_answer_does_not_pause_again() -> None:

    """With two deletes, a reject without reply refuses both instead of pausing for the second."""

    calls = [call("delete_record", LOAN_ARGS, "del"), call("delete_record", CAR_ARGS, "del2")]

    graph, config, context, _ = await pause(calls)

    result = await graph.ainvoke(Command(resume=answer(REJECT, reply=False)), config, context=context)

    assert "__interrupt__" not in result
    assert ran == []


async def test_two_deletes_pause_one_at_a_time() -> None:

    """With two deletes, approving the first pauses again for the second."""

    calls = [call("delete_record", LOAN_ARGS, "del"), call("delete_record", CAR_ARGS, "del2")]

    graph, config, context, _ = await pause(calls)

    result = await graph.ainvoke(Command(resume=answer(APPROVE)), config, context=context)

    assert result["__interrupt__"][0].value["tool_call_id"] == "del2"

    await graph.ainvoke(Command(resume=answer(APPROVE, "del2", CAR_ARGS)), config, context=context)

    assert sorted(ran) == ["delete_record:42", "delete_record:7"]
