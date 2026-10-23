"""Tests for the per-turn limits on model calls, tool calls and output tokens, on an in-memory graph with a fake model."""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command

from app.agent import approval, nodes
from app.agent.approval import APPROVE, approval_gate
from app.agent.budget import (
    MODEL_CALL_LIMIT,
    OUTPUT_TOKEN_LIMIT,
    TOOL_CALL_LIMIT,
    add_model_call,
    cost_usd,
    limit_reached,
    new_budget,
    )
from app.agent.context import PlannerContext
from app.agent.graph import after_tools
from app.agent.nodes import AGENT_NODE, APPROVAL_NODE, FALLBACK_TEXT, TOOLS_NODE, run_agent
from app.agent.state import PlannerState
from app.core.config import get_settings


WRAP_UP_TEXT = "I saved your rent. Your SIPs are still left."

ran: list[str] = []


@tool
def list_records(kind: str) -> str:

    """Pretend to read saved items."""

    ran.append("list_records")

    return "nothing saved"


@tool
def delete_record(kind: str, record_id: int) -> str:

    """Pretend to remove a saved item."""

    ran.append("delete_record")

    return "removed"


def usage(output_tokens: int) -> dict[str, int]:

    """Token usage as the model reports it on its last streamed piece."""

    return {"input_tokens": 100, "output_tokens": output_tokens, "total_tokens": 100 + output_tokens}


class ToolAsker:

    """A model that asks for the same tool calls on every call, reporting the given output tokens."""

    def __init__(self, calls: list[dict[str, Any]], output_tokens: int = 50) -> None:

        """Keep the calls to ask for and the tokens to report."""

        self.calls = calls
        self.output_tokens = output_tokens
        self.count = 0

    async def astream(self, messages: list) -> AsyncIterator[AIMessageChunk]:

        """Ask for the tool calls, each with a fresh id."""

        self.count += 1

        chunks = [
            {"name": call["name"], "args": call["args"], "id": f"{call['name']}-{self.count}-{index}", "index": index}
            for index, call in enumerate(self.calls)
            ]

        yield AIMessageChunk("", tool_call_chunks=[{**chunk, "args": str(chunk["args"]).replace("'", '"')} for chunk in chunks])

        yield AIMessageChunk("", usage_metadata=usage(self.output_tokens))


class Closer:

    """The wrap-up model: answers in one line, or fails when asked to."""

    def __init__(self, fail: bool = False) -> None:

        """Remember whether to fail and what it was shown."""

        self.fail = fail
        self.seen: list = []

    async def astream(self, messages: list) -> AsyncIterator[AIMessageChunk]:

        """Answer with the closing line, or raise."""

        self.seen = messages

        if self.fail:
            raise RuntimeError("model is down")

        yield AIMessageChunk(WRAP_UP_TEXT, usage_metadata=usage(20))


def install(monkeypatch: pytest.MonkeyPatch, asker: ToolAsker, closer: Closer) -> None:

    """Make run_agent use the fake models."""

    monkeypatch.setattr(nodes.llm_service, "with_tools", lambda tools, model=None, max_tokens=None: asker)
    monkeypatch.setattr(nodes.llm_service, "without_acting", lambda tools, max_tokens, model=None: closer)


def build():

    """The planner's agent, gate and tools loop, without the memory loader, on an in-memory checkpointer."""

    builder = StateGraph(PlannerState, context_schema=PlannerContext)

    builder.add_node(AGENT_NODE, run_agent)
    builder.add_node(APPROVAL_NODE, approval_gate, destinations=(TOOLS_NODE, AGENT_NODE, END))
    builder.add_node(TOOLS_NODE, ToolNode([list_records, delete_record]))

    builder.add_edge(START, AGENT_NODE)
    builder.add_conditional_edges(AGENT_NODE, tools_condition, {"tools": APPROVAL_NODE, END: END})
    builder.add_conditional_edges(TOOLS_NODE, after_tools, [AGENT_NODE, END])

    return builder.compile(checkpointer=InMemorySaver())


async def run_turn(graph=None) -> tuple[Any, dict, dict]:

    """Run one turn from a user message with a fresh budget, and return the graph, its config and the end state."""

    graph = graph or build()
    config = {"configurable": {"thread_id": "test"}}

    state = await graph.ainvoke(
        {"messages": [HumanMessage("add everything")], "budget": new_budget()},
        config,
        context=PlannerContext(user_id=1),
        )

    return graph, config, state


@pytest.fixture(autouse=True)
def small_limits(monkeypatch: pytest.MonkeyPatch) -> None:

    """Shrink the limits so a turn reaches them in a few steps, and clear the record of tools that ran."""

    settings = get_settings()

    monkeypatch.setattr(settings, "MAX_MODEL_CALLS", 3)
    monkeypatch.setattr(settings, "MAX_TOOL_CALLS", 20)
    monkeypatch.setattr(settings, "MAX_OUTPUT_TOKENS_PER_TURN", 12000)

    ran.clear()


def test_budget_counts_tokens_and_cost() -> None:

    """A model call adds its tokens, and the cost uses the model's price, or nothing for an unknown model."""

    answer = AIMessageChunk("", usage_metadata={"input_tokens": 1_000_000, "output_tokens": 1_000_000, "total_tokens": 2_000_000})

    budget = add_model_call(new_budget(), answer)

    assert budget["model_calls"] == 1
    assert cost_usd(budget, "gpt-4o-mini") == Decimal("0.75")
    assert cost_usd(budget, "some-other-model") is None


def test_limit_order() -> None:

    """A limit already marked wins, then the model call count, then the output tokens."""

    assert limit_reached(new_budget()) is None
    assert limit_reached({**new_budget(), "model_calls": 3}) == MODEL_CALL_LIMIT
    assert limit_reached({**new_budget(), "output_tokens": 12000}) == OUTPUT_TOKEN_LIMIT
    assert limit_reached({**new_budget(), "model_calls": 3, "limit": TOOL_CALL_LIMIT}) == TOOL_CALL_LIMIT


async def test_model_call_limit_ends_with_a_wrap_up(monkeypatch: pytest.MonkeyPatch) -> None:

    """A model that keeps asking for tools is stopped at the limit, and the turn ends with a closing reply."""

    closer = Closer()

    install(monkeypatch, ToolAsker([{"name": "list_records", "args": {"kind": "loans"}}]), closer)

    _, _, state = await run_turn()

    assert state["messages"][-1].content == WRAP_UP_TEXT
    assert state["budget"]["limit"] == MODEL_CALL_LIMIT
    assert state["budget"]["model_calls"] == 4
    assert ran == ["list_records"] * 3
    assert "Do not call any tool" in closer.seen[-1].content


async def test_output_token_limit_ends_with_a_wrap_up(monkeypatch: pytest.MonkeyPatch) -> None:

    """A turn that has written past its token budget wraps up before the next model call."""

    install(monkeypatch, ToolAsker([{"name": "list_records", "args": {"kind": "loans"}}], output_tokens=13000), Closer())

    _, _, state = await run_turn()

    assert state["messages"][-1].content == WRAP_UP_TEXT
    assert state["budget"]["limit"] == OUTPUT_TOKEN_LIMIT
    assert ran == ["list_records"]


async def test_tool_call_limit_refuses_the_batch_and_wraps_up(monkeypatch: pytest.MonkeyPatch) -> None:

    """A batch that would pass the tool limit does not run; each call is refused and the model closes the turn."""

    monkeypatch.setattr(get_settings(), "MAX_TOOL_CALLS", 1)

    calls = [{"name": "list_records", "args": {"kind": "loans"}}, {"name": "list_records", "args": {"kind": "goals"}}]

    install(monkeypatch, ToolAsker(calls), Closer())

    _, _, state = await run_turn()

    refused = [message for message in state["messages"] if isinstance(message, ToolMessage)]

    assert ran == []
    assert [message.artifact["error_code"] for message in refused] == [TOOL_CALL_LIMIT, TOOL_CALL_LIMIT]
    assert state["budget"]["limit"] == TOOL_CALL_LIMIT
    assert state["messages"][-1].content == WRAP_UP_TEXT


async def test_failed_wrap_up_falls_back_to_a_kind_line(monkeypatch: pytest.MonkeyPatch) -> None:

    """When the closing reply itself fails, the turn still ends with the fixed line, streamed like any reply, instead of an error."""

    install(monkeypatch, ToolAsker([{"name": "list_records", "args": {"kind": "loans"}}]), Closer(fail=True))

    streamed = []

    async for message, _ in build().astream(
        {"messages": [HumanMessage("add everything")], "budget": new_budget()},
        {"configurable": {"thread_id": "test"}},
        context=PlannerContext(user_id=1),
        stream_mode="messages",
        ):

        if isinstance(message, AIMessageChunk) and message.content:
            streamed.append(message.content)

    assert streamed == [FALLBACK_TEXT]


async def test_counts_carry_on_after_an_approval(monkeypatch: pytest.MonkeyPatch) -> None:

    """Approving a card continues the same turn, so the budget keeps its counts instead of starting again."""

    async def preview(call: dict[str, Any], user_id: int) -> dict[str, Any]:

        """A fixed preview for the delete."""

        return {"action": "remove", "title": "Remove this loan?", "fields": []}

    monkeypatch.setattr(approval, "preview_for", preview)

    install(monkeypatch, ToolAsker([{"name": "delete_record", "args": {"kind": "loans", "record_id": 42}}]), Closer())

    graph, config, paused = await run_turn()

    request = paused["__interrupt__"][0].value

    assert paused["budget"]["model_calls"] == 1

    answer = {"decision": APPROVE, "tool_call_id": request["tool_call_id"], "arguments": request["args"], "reply": True}

    resumed = await graph.ainvoke(Command(resume=answer), config, context=PlannerContext(user_id=1))

    assert ran[0] == "delete_record"
    assert resumed["budget"]["model_calls"] >= 2
    assert resumed["budget"]["tool_calls"] >= 1
