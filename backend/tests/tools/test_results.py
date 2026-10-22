"""Tests for the typed tool result helpers and the tool call wrapper, with no database."""

import pytest
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy.exc import OperationalError

from app.agent.tools import policies
from app.agent.tools.results import (
    finish_tool_call,
    from_record_error,
    from_validation_error,
    ok,
    rejected,
    to_message,
    )
from app.features.records.exceptions import RecordConflict, RecordError, RecordExists, RecordNotFound


class Rate(BaseModel):

    """A small schema with one rule, to produce a real validation error."""

    rate: int

    @field_validator("rate")
    @classmethod
    def under_hundred(cls, value: int) -> int:

        """Refuse a rate of 100 or more."""

        if value >= 100:
            raise ValueError("must be under 100")

        return value


def test_record_errors_map_to_their_status() -> None:

    """A duplicate is a conflict with the existing id, a missing item is not found, a link is a conflict, the rest is validation."""

    exists = from_record_error(RecordExists("loan", 3))
    missing = from_record_error(RecordNotFound("No loan with id 42."))
    linked = from_record_error(RecordConflict("Cannot remove this family member: goal id 5 is linked to it."))
    refused = from_record_error(RecordError("Nothing to update."))

    assert (exists.status, exists.error_code, exists.data) == ("conflict", "already_exists", {"existing_id": 3})
    assert (missing.status, missing.error_code) == ("not_found", "not_found")
    assert (linked.status, linked.error_code) == ("conflict", "linked_items")
    assert (refused.status, refused.error_code, refused.message) == ("validation_error", "refused", "Nothing to update.")


def test_validation_error_lists_each_field() -> None:

    """A pydantic error becomes one validation result naming the field and its problem."""

    try:
        Rate(rate=120)

    except ValidationError as exc:
        result = from_validation_error(exc)

    assert result.status == "validation_error"
    assert result.error_code == "invalid_values"
    assert result.data["errors"][0]["field"] == "rate"
    assert "must be under 100" in result.data["errors"][0]["problem"]


def test_success_message_is_marked_success() -> None:

    """A success becomes a success tool message with the JSON as content and the whole result as the artifact."""

    message = to_message(ok("Saved loan.", {"id": 7}), "call-1", "add_loan")

    assert message.status == "success"
    assert message.name == "add_loan"
    assert '"status":"success"' in message.content
    assert message.artifact == {"status": "success", "message": "Saved loan.", "data": {"id": 7}, "retryable": False}


def test_failure_message_is_marked_error() -> None:

    """Any status other than success makes the tool message an error, so the worker saves it as failed."""

    message = to_message(rejected("user_rejected", "Not done."), "call-1")

    assert message.status == "error"
    assert message.artifact["status"] == "rejected"


def test_extra_text_is_sent_as_its_own_block() -> None:

    """A report goes in a second text block after the JSON, so its backslashes are not escaped."""

    report = r"$$ \frac{a}{b} $$"

    message = to_message(ok("Report follows."), "call-1", extra_text=report)

    assert message.content[1] == {"type": "text", "text": report}
    assert message.content[0]["text"].startswith('{"status":"success"')


@tool
async def database_down(runtime: ToolRuntime) -> ToolMessage:

    """A tool whose database cannot be reached."""

    raise OperationalError("SELECT 1", {}, Exception("connection refused"))


@tool
async def saves_fine(runtime: ToolRuntime) -> ToolMessage:

    """A tool that saves and returns its own message without a name."""

    return to_message(ok("Saved."), runtime.tool_call_id)


@pytest.fixture(autouse=True)
def allow_test_tools(monkeypatch: pytest.MonkeyPatch) -> None:

    """Give the two test tools a write policy, since the wrapper refuses any tool without one."""

    monkeypatch.setitem(policies.TOOL_POLICIES, "database_down", policies.WRITE)
    monkeypatch.setitem(policies.TOOL_POLICIES, "saves_fine", policies.WRITE)


async def run_tools(*names: str) -> list[ToolMessage]:

    """Call the named tools once each through a ToolNode with the wrapper, and return their messages."""

    builder = StateGraph(MessagesState)

    builder.add_node("tools", ToolNode([database_down, saves_fine], awrap_tool_call=finish_tool_call))
    builder.add_edge(START, "tools")

    calls = [{"name": name, "args": {}, "id": f"call-{index}"} for index, name in enumerate(names)]

    result = await builder.compile().ainvoke({"messages": [AIMessage("", tool_calls=calls)]})

    return result["messages"][1:]


async def test_wrapper_turns_a_database_outage_into_retryable() -> None:

    """A database error inside a tool comes back as a retryable error instead of failing the run."""

    [message] = await run_tools("database_down")

    assert message.status == "error"
    assert message.artifact["status"] == "retryable_error"
    assert message.artifact["retryable"] is True


async def test_wrapper_stamps_the_tool_name() -> None:

    """A message a tool built itself gets the tool's name, which the worker needs for its events."""

    [message] = await run_tools("saves_fine")

    assert message.name == "saves_fine"
    assert message.status == "success"
