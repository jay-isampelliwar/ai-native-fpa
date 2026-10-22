"""The one shape every tool returns, the helpers that build it, and the wrapper that turns it into a tool message."""

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import OperationalError

from app.features.records.exceptions import RecordConflict, RecordError, RecordExists, RecordNotFound


type ToolStatus = Literal["success", "validation_error", "not_found", "conflict", "retryable_error", "rejected"]

type ToolExecute = Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]]


class ToolResult(BaseModel):

    """What every tool returns: a fixed status the code can switch on, a message the model can repeat, and the data."""

    status: ToolStatus
    message: str
    data: dict[str, Any] | None = None
    error_code: str | None = None
    retryable: bool = False


def ok(
    message: str,
    data: dict[str, Any] | None = None,
    ) -> ToolResult:

    """The tool did what was asked."""

    return ToolResult(status="success", message=message, data=data)


def invalid(
    error_code: str,
    message: str,
    data: dict[str, Any] | None = None,
    ) -> ToolResult:

    """Something the user gave is missing or wrong, so the model should ask them to correct it."""

    return ToolResult(status="validation_error", message=message, data=data, error_code=error_code)


def not_found(
    message: str,
    data: dict[str, Any] | None = None,
    ) -> ToolResult:

    """The item the call points at is not saved for this user."""

    return ToolResult(status="not_found", message=message, data=data, error_code="not_found")


def conflict(
    error_code: str,
    message: str,
    data: dict[str, Any] | None = None,
    ) -> ToolResult:

    """The change clashes with something already saved, so it was refused."""

    return ToolResult(status="conflict", message=message, data=data, error_code=error_code)


def retryable(message: str) -> ToolResult:

    """The database could not be reached, so nothing is known to be saved and the user can try again."""

    return ToolResult(status="retryable_error", message=message, error_code="db_unavailable", retryable=True)


def rejected(
    error_code: str,
    message: str,
    ) -> ToolResult:

    """The user did not approve the call, or stopped the reply, so it never ran."""

    return ToolResult(status="rejected", message=message, error_code=error_code)


def field_errors(exc: ValidationError) -> list[dict[str, str]]:

    """List each pydantic error as the field it is about and the problem in plain words."""

    return [
        {"field": ".".join(str(part) for part in error["loc"]) or "details", "problem": error["msg"]}
        for error in exc.errors()
        ]


def from_validation_error(exc: ValidationError) -> ToolResult:

    """Turn pydantic errors into one validation result, with a short line and every field's problem."""

    errors = field_errors(exc)

    message = "; ".join(f"{error['field']}: {error['problem']}" for error in errors)

    return invalid("invalid_values", message, {"errors": errors})


def from_record_error(exc: RecordError) -> ToolResult:

    """Turn a refusal from a record service into not found, conflict or validation, keeping its message."""

    if isinstance(exc, RecordExists):
        return conflict("already_exists", str(exc), {"existing_id": exc.record_id})

    if isinstance(exc, RecordNotFound):
        return not_found(str(exc))

    if isinstance(exc, RecordConflict):
        return conflict("linked_items", str(exc))

    return invalid("refused", str(exc))


def to_message(
    result: ToolResult,
    tool_call_id: str,
    name: str | None = None,
    extra_text: str | None = None,
    ) -> ToolMessage:

    """Send the result as JSON to the model, marked error unless it succeeded, with the result kept whole as the artifact."""

    content: str | list[dict[str, str]] = result.model_dump_json(exclude_none=True)

    if extra_text is not None:
        content = [{"type": "text", "text": content}, {"type": "text", "text": extra_text}]

    return ToolMessage(
        content,
        tool_call_id=tool_call_id,
        name=name,
        status="success" if result.status == "success" else "error",
        artifact=result.model_dump(mode="json", exclude_none=True),
        )


async def finish_tool_call(
    request: ToolCallRequest,
    execute: ToolExecute,
    ) -> ToolMessage | Command:

    """Run one tool, answer a database outage as retryable, and stamp the tool's name on the message it returns."""

    call = request.tool_call

    try:
        message = await execute(request)

    except OperationalError:
        return to_message(retryable("Could not reach the database, so this may not have been saved."), call["id"], call["name"])

    if isinstance(message, ToolMessage):
        message.name = call["name"]

    return message
