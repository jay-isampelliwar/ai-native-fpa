"""Tests for the guards that need no database: fund houses as banks, clean errors, crashing tools, stopping repeats, and reply spacing."""

import json

import pytest
from langchain.tools import tool
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.cancellation import RunCancelled
from app.agent.context import PlannerContext
from app.agent.tools import policies
from app.agent.tools.policies import needs_approval
from app.agent.tools.results import ToolResult, invalid
from app.agent.tools.wrapper import failure_sign, finish_tool_call, invocation_error, keeps_failing
from app.features.assets.fund_houses import is_fund_house, is_shared_brand, refuse_fund_house
from app.features.records.exceptions import RecordError
from app.features.runs.worker import spaced


runs: list[str] = []


@tool
def lookup(query: str) -> str:

    """A fake read tool that needs a query."""

    runs.append(query)

    return invalid("not_found_here", "Nothing matched.").model_dump_json()


def failed(text: str = "Nothing matched.", code: str = "not_found_here") -> ToolMessage:

    """One failed lookup result as the model would see it."""

    content = ToolResult(status="validation_error", message=text, error_code=code).model_dump_json()

    return ToolMessage(content, tool_call_id="old", name="lookup", status="error")


def state_with(*results: ToolMessage) -> dict:

    """A reply's state: the user's message, then the given tool results."""

    return {"messages": [HumanMessage("find it"), *results]}


@pytest.mark.parametrize("name", ["Nippon", "Nippon Life India Asset Management Limited", "Axis Mutual Fund", "HDFC AMC", "Quant"])
def test_fund_houses_are_refused_as_banks(name: str) -> None:

    """A name that can only be a fund house is refused for a fixed deposit."""

    assert is_fund_house(name)

    with pytest.raises(RecordError):
        refuse_fund_house(name)


@pytest.mark.parametrize("name", ["Axis Bank", "HDFC", "SBI", "Bank of Baroda", "Kotak Mahindra Bank"])
def test_banks_that_also_run_funds_need_a_card(name: str) -> None:

    """A bank that also runs funds is allowed, but the user must confirm it on a card."""

    assert not is_fund_house(name)
    assert is_shared_brand(name)
    assert needs_approval("add_fixed_deposit", {"bank_name": name})


@pytest.mark.parametrize("name", ["Post Office", "Indian Bank", "Federal Bank"])
def test_plain_banks_save_without_a_card(name: str) -> None:

    """A bank that runs no funds saves without asking."""

    assert not is_fund_house(name)
    assert not needs_approval("add_fixed_deposit", {"bank_name": name})


def test_three_same_failures_mean_stop() -> None:

    """Three failed results with the same error in this reply stop the tool."""

    assert keeps_failing(state_with(failed(), failed(), failed()), "lookup")


def test_different_errors_or_fewer_failures_do_not_stop() -> None:

    """Two failures, or three different ones, let the tool run again."""

    assert not keeps_failing(state_with(failed(), failed()), "lookup")
    assert not keeps_failing(state_with(failed("A"), failed("B"), failed("C")), "lookup")


def test_failures_before_the_users_message_do_not_count() -> None:

    """Failures from an earlier reply are not counted in this one."""

    state = {"messages": [failed(), failed(), failed(), HumanMessage("try again")]}

    assert not keeps_failing(state, "lookup")


def test_a_turned_down_call_is_not_a_failure() -> None:

    """A call the user rejected on a card does not count as a failure."""

    content = ToolResult(status="rejected", message="Not done.", error_code="user_rejected").model_dump_json()

    assert failure_sign(ToolMessage(content, tool_call_id="x", name="lookup", status="error")) is None


def graph():

    """A tools node with the real wrapper and error handler around the fake lookup tool."""

    builder = StateGraph(MessagesState, context_schema=PlannerContext)

    builder.add_node("tools", ToolNode([lookup], awrap_tool_call=finish_tool_call, handle_tool_errors=invocation_error))
    builder.add_edge(START, "tools")

    return builder.compile()


def call(args: dict) -> AIMessage:

    """The model asking for one lookup call."""

    return AIMessage("", tool_calls=[{"name": "lookup", "args": args, "id": "new"}])


async def test_a_missing_argument_comes_back_as_a_clean_result(monkeypatch: pytest.MonkeyPatch) -> None:

    """A call with no query returns a validation result naming the field, not raw error text."""

    monkeypatch.setitem(policies.TOOL_POLICIES, "lookup", policies.READ)

    result = await graph().ainvoke({"messages": [HumanMessage("find"), call({})]}, context=PlannerContext(user_id=1))

    body = json.loads(result["messages"][-1].content)

    assert body["status"] == "validation_error"
    assert body["error_code"] == "invalid_arguments"
    assert body["data"]["errors"][0]["field"] == "query"


async def test_the_fourth_same_failure_is_not_run(monkeypatch: pytest.MonkeyPatch) -> None:

    """After three same failures in this reply, the next call is refused without running the tool."""

    monkeypatch.setitem(policies.TOOL_POLICIES, "lookup", policies.READ)

    runs.clear()

    state = {"messages": [HumanMessage("find"), failed(), failed(), failed(), call({"query": "x"})]}

    result = await graph().ainvoke(state, context=PlannerContext(user_id=1))

    body = json.loads(result["messages"][-1].content)

    assert runs == []
    assert body["error_code"] == "repeated_failure"


@tool
def broken() -> str:

    """A fake tool that crashes the way a missing method does."""

    raise AttributeError("'BaseUserRecordRepository' object has no attribute 'list_for_user'")


async def test_a_crashing_tool_gives_a_failed_result_and_the_run_goes_on(monkeypatch: pytest.MonkeyPatch) -> None:

    """A tool that raises an AttributeError comes back as tool_failed instead of failing the whole run."""

    monkeypatch.setitem(policies.TOOL_POLICIES, "broken", policies.READ)

    builder = StateGraph(MessagesState, context_schema=PlannerContext)

    builder.add_node("tools", ToolNode([broken], awrap_tool_call=finish_tool_call, handle_tool_errors=invocation_error))
    builder.add_edge(START, "tools")

    asked = AIMessage("", tool_calls=[{"name": "broken", "args": {}, "id": "b1"}])

    result = await builder.compile().ainvoke({"messages": [HumanMessage("check"), asked]}, context=PlannerContext(user_id=1))

    body = json.loads(result["messages"][-1].content)

    assert body["error_code"] == "tool_failed"
    assert "broken" in body["message"]


def test_a_stop_request_is_not_turned_into_a_result() -> None:

    """A run asked to stop still stops, instead of becoming a tool result."""

    with pytest.raises(RunCancelled):
        invocation_error(RunCancelled(7))


def test_any_other_crash_becomes_a_failed_result() -> None:

    """A crash that is not about arguments becomes a tool_failed result."""

    body = json.loads(invocation_error(AttributeError("no such method")))

    assert body["error_code"] == "tool_failed"


def test_text_after_tools_starts_a_new_paragraph() -> None:

    """Text that follows tool steps gets a paragraph break, and the first text does not."""

    assert spaced("I found them.", True) == "\n\nI found them."
    assert spaced("Hello", False) == "Hello"
