"""Tests for tool timeouts and retries in the tool call wrapper, with fake tools and no database."""

import asyncio
import time
from typing import Any

import pytest
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode
from sqlalchemy.exc import OperationalError

from app.agent.context import PlannerContext
from app.agent.state import PlannerState
from app.agent.tools import policies
from app.agent.tools.results import invalid, ok, to_message
from app.agent.tools.wrapper import finish_tool_call
from app.core.config import get_settings


runs: dict[str, int] = {}


def count(name: str) -> int:

    """Count one run of a fake tool and return which run this is, starting at 1."""

    runs[name] = runs.get(name, 0) + 1

    return runs[name]


@tool
async def slow_twice(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """Hang on its first two runs, then answer."""

    if count("slow_twice") <= 2:
        await asyncio.sleep(1)

    return to_message(ok("Read."), runtime.tool_call_id)


@tool
async def always_slow(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """Hang every time."""

    count("always_slow")

    await asyncio.sleep(1)

    return to_message(ok("Never."), runtime.tool_call_id)


@tool
async def outage_once(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """Lose the database on the first run, then answer."""

    if count("outage_once") == 1:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    return to_message(ok("Read."), runtime.tool_call_id)


@tool
async def bad_input(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """Refuse what the user gave, which is never worth a retry."""

    count("bad_input")

    return to_message(invalid("missing_fields", "Required details missing."), runtime.tool_call_id)


@tool
async def slow_write(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """A write that hangs every time."""

    count("slow_write")

    await asyncio.sleep(1)

    return to_message(ok("Saved."), runtime.tool_call_id)


TOOLS = [slow_twice, always_slow, outage_once, bad_input, slow_write]


@pytest.fixture(autouse=True)
def fast_limits(monkeypatch: pytest.MonkeyPatch) -> None:

    """Shrink every limit so the tests run in a moment, give the fake tools policies, and clear the run counts."""

    settings = get_settings()

    monkeypatch.setattr(settings, "TOOL_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(settings, "TOOL_RETRY_BASE_SECONDS", 0.01)
    monkeypatch.setattr(settings, "MIN_RETRY_SECONDS", 0)

    for name in ("slow_twice", "always_slow", "outage_once", "bad_input"):
        monkeypatch.setitem(policies.TOOL_POLICIES, name, policies.READ)

    monkeypatch.setitem(policies.TOOL_POLICIES, "slow_write", policies.WRITE)

    runs.clear()


async def call(name: str, context: PlannerContext | None = None) -> ToolMessage:

    """Run one call of a fake tool through the wrapper and return its message."""

    builder = StateGraph(PlannerState, context_schema=PlannerContext)

    builder.add_node("tools", ToolNode(TOOLS, awrap_tool_call=finish_tool_call))
    builder.add_edge(START, "tools")

    calls: list[dict[str, Any]] = [{"name": name, "args": {}, "id": "call-1"}]

    result = await builder.compile().ainvoke(
        {"messages": [AIMessage("", tool_calls=calls)]},
        context=context or PlannerContext(user_id=1),
        )

    return result["messages"][-1]


async def test_timeout_then_success_retries_until_it_works() -> None:

    """A read that hangs twice and then answers succeeds on the third try."""

    message = await call("slow_twice")

    assert message.artifact["status"] == "success"
    assert runs["slow_twice"] == 3


async def test_gives_up_after_the_last_try() -> None:

    """A read that always hangs is a retryable timeout after three tries."""

    message = await call("always_slow")

    assert message.status == "error"
    assert message.artifact["status"] == "retryable_error"
    assert message.artifact["error_code"] == "database_timeout"
    assert runs["always_slow"] == 3


async def test_outage_is_retried() -> None:

    """A lost database connection is retried, and the second try answers."""

    message = await call("outage_once")

    assert message.artifact["status"] == "success"
    assert runs["outage_once"] == 2


async def test_refused_input_is_not_retried() -> None:

    """A validation error is an answer, not a failure, so the tool runs once."""

    message = await call("bad_input")

    assert message.artifact["status"] == "validation_error"
    assert runs["bad_input"] == 1


async def test_write_outside_a_conversation_is_not_retried() -> None:

    """With no conversation the idempotency guard is off, so a write that times out runs only once."""

    message = await call("slow_write")

    assert message.artifact["status"] == "retryable_error"
    assert runs["slow_write"] == 1


async def test_write_inside_a_conversation_is_retried() -> None:

    """Inside a conversation the guard stops a second write, so a write that times out is tried again."""

    message = await call("slow_write", PlannerContext(user_id=1, conversation_id=5))

    assert message.artifact["status"] == "retryable_error"
    assert runs["slow_write"] == 3


async def test_no_retry_when_the_turn_is_almost_over(monkeypatch: pytest.MonkeyPatch) -> None:

    """When less than the minimum is left in the turn, a timeout is answered at once instead of tried again."""

    monkeypatch.setattr(get_settings(), "MIN_RETRY_SECONDS", 2)

    message = await call("always_slow", PlannerContext(user_id=1, deadline=time.monotonic() + 1))

    assert message.artifact["status"] == "retryable_error"
    assert runs["always_slow"] == 1


async def test_tool_timeout_is_capped_by_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:

    """A tool gets only the time the turn has left, even when its own limit is longer."""

    monkeypatch.setattr(get_settings(), "TOOL_TIMEOUT_SECONDS", 10)
    monkeypatch.setattr(get_settings(), "MIN_RETRY_SECONDS", 2)

    started = time.monotonic()

    message = await call("always_slow", PlannerContext(user_id=1, deadline=time.monotonic() + 0.1))

    assert message.artifact["status"] == "retryable_error"
    assert time.monotonic() - started < 0.5


async def test_cancel_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:

    """Stopping the reply while a tool runs cancels it at once, with no retry."""

    monkeypatch.setattr(get_settings(), "TOOL_TIMEOUT_SECONDS", 10)

    task = asyncio.create_task(call("always_slow"))

    await asyncio.sleep(0.05)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert runs["always_slow"] == 1
