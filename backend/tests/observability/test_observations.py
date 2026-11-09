"""Tests for the small Langfuse steps inside graph nodes, with the client faked so no key or network is needed."""

import asyncio
from typing import Any

import pytest
from langgraph.errors import GraphInterrupt
from langgraph.types import Command, Send

from app.agent.approval import next_node
from app.agent.tools.results import not_allowed, ok, rejected, retryable, to_message, tool_failed
from app.agent.tools.wrapper import guard_outcome
from app.core.config import get_settings
from app.observability import observations
from app.observability.observations import CANCELLED, PAUSED, end_step, observe_step, open_step, update_step


class FakeStep:

    """Stands in for a Langfuse step, keeping every update and whether it was ended."""

    def __init__(self, **kwargs: Any) -> None:

        """Remember how the step was started."""

        self.started = kwargs
        self.updates: list[dict[str, Any]] = []
        self.ended = False

    def update(self, **fields: Any) -> None:

        """Keep the update instead of sending it."""

        self.updates.append(fields)

    def __enter__(self) -> "FakeStep":

        """Become the current step."""

        return self

    def __exit__(self, *args: Any) -> None:

        """Mark the step as ended instead of sending it."""

        self.ended = True


class FakeClient:

    """Stands in for the Langfuse client, keeping every step it started."""

    def __init__(self) -> None:

        """Start with no steps."""

        self.steps: list[FakeStep] = []

    def start_as_current_observation(self, **kwargs: Any) -> FakeStep:

        """Start a fake step and keep it."""

        step = FakeStep(**kwargs)

        self.steps.append(step)

        return step


class BrokenClient:

    """Stands in for a client that cannot start a step, the way it would when Langfuse is down."""

    def start_as_current_observation(self, **kwargs: Any) -> FakeStep:

        """Fail like a broken start."""

        raise RuntimeError("langfuse is down")


class BrokenStep:

    """Stands in for a step whose every call breaks, the way it would when Langfuse is down."""

    def update(self, **fields: Any) -> None:

        """Fail like a broken update."""

        raise RuntimeError("langfuse is down")

    def __exit__(self, *args: Any) -> None:

        """Fail like a broken end."""

        raise RuntimeError("langfuse is down")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:

    """Turn tracing on with a fake client for one test."""

    fake = FakeClient()

    monkeypatch.setattr(observations, "create_langfuse", lambda settings: fake)

    return fake


async def test_no_step_when_tracing_is_off() -> None:

    """With tracing off the block still runs and gets no step."""

    async with observe_step(get_settings(), "read-memories", "retriever") as step:
        ran = True

    assert step is None
    assert ran


async def test_a_step_is_started_with_its_name_type_and_metadata_then_ended(client: FakeClient) -> None:

    """The step gets the name, type and counts it was given, and is ended when the block finishes."""

    async with observe_step(get_settings(), "read-memories", "retriever", {"limit": 50}) as step:
        update_step(step, metadata={"memory_count": 3})

    started = client.steps[0]

    assert started.started == {"name": "read-memories", "as_type": "retriever", "metadata": {"limit": 50}}
    assert started.updates == [{"metadata": {"memory_count": 3}}]
    assert started.ended


async def test_a_crash_marks_the_step_as_an_error_by_type_only_and_is_raised(client: FakeClient) -> None:

    """A crash inside the block is raised as before, and the step says only the error's type, never its text."""

    with pytest.raises(ValueError):

        async with observe_step(get_settings(), "approval-check", "guardrail"):
            raise ValueError("balance 12,00,000")

    started = client.steps[0]

    assert started.updates == [{"level": "ERROR", "status_message": "ValueError"}]
    assert started.ended


async def test_a_pause_for_the_user_is_marked_paused_not_an_error(client: FakeClient) -> None:

    """An approval pause passes through and the step says paused, with no error level."""

    with pytest.raises(GraphInterrupt):

        async with observe_step(get_settings(), "approval-check", "guardrail"):
            raise GraphInterrupt()

    started = client.steps[0]

    assert started.updates == [{"metadata": {"outcome": PAUSED}}]
    assert started.ended


async def test_a_cut_off_step_is_a_cancelled_warning(client: FakeClient) -> None:

    """A step cut off by a tool timeout says cancelled as a warning, and the cancel passes through."""

    with pytest.raises(asyncio.CancelledError):

        async with observe_step(get_settings(), "tavily.search", "span"):
            raise asyncio.CancelledError()

    started = client.steps[0]

    assert started.updates == [{"level": "WARNING", "status_message": CANCELLED}]
    assert started.ended


def test_a_step_that_fails_to_start_is_logged_and_skipped(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    ) -> None:

    """A broken client gives no step and a logged error, and the block still runs."""

    monkeypatch.setattr(observations, "create_langfuse", lambda settings: BrokenClient())

    assert open_step(get_settings(), "read-memories", "retriever") is None
    assert "failed to start" in caplog.text


def test_a_broken_update_or_end_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:

    """A step that breaks on update or end never fails the node."""

    update_step(BrokenStep(), metadata={"memory_count": 3})
    end_step((BrokenStep(), BrokenStep()))

    assert "failed to update" in caplog.text
    assert "failed to end" in caplog.text


def test_the_approval_outcome_names_the_next_node() -> None:

    """The approval step says where the turn goes, whether by name or by a send to the tools."""

    assert next_node(Command(goto="agent")) == "agent"
    assert next_node(Command(goto=Send("tools", []))) == "tools"


def test_a_refused_tool_call_is_a_warning_with_its_error_code() -> None:

    """A call refused for having no policy is a warning that names its status and error code, with no tool output."""

    outcome = guard_outcome(to_message(not_allowed("get_holdings"), "call-1", "get_holdings"))

    assert outcome["level"] == "WARNING"
    assert outcome["metadata"]["status"] == "not_allowed"
    assert outcome["metadata"]["error_code"] == "no_policy"
    assert outcome["status_message"] == "not_allowed: no_policy"


def test_a_successful_tool_call_is_plain_with_no_message() -> None:

    """A call that worked is plain, with its status and nothing about its result."""

    outcome = guard_outcome(to_message(ok("Found 2 funds.", {"funds": 2}), "call-1", "get_holdings"))

    assert outcome == {"metadata": {"status": "success", "error_code": None, "retryable": False}, "level": "DEFAULT"}


def test_tries_used_up_or_a_crash_is_an_error() -> None:

    """A retryable failure left after every try, or a crashed tool, is an error."""

    assert guard_outcome(to_message(retryable("Database down.", "db_unavailable"), "call-1", "get_holdings"))["level"] == "ERROR"
    assert guard_outcome(to_message(tool_failed("get_holdings"), "call-1", "get_holdings"))["level"] == "ERROR"


def test_a_user_no_is_plain() -> None:

    """The user turning a change down is a normal answer, not a problem."""

    outcome = guard_outcome(to_message(rejected("user_rejected", "Not done."), "call-1", "delete_record"))

    assert outcome["level"] == "DEFAULT"
