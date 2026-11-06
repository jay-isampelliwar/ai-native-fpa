"""The one shape every tool returns, the helpers that build it, and the step that turns it into a tool message."""

from typing import Any, Literal

from langchain_core.messages import ToolMessage
from pydantic import BaseModel, ValidationError

from app.features.records.exceptions import HoldingMissing, RecordConflict, RecordError, RecordExists, RecordNotFound


REPEAT_LIMIT = 3


type ToolStatus = Literal[
    "success",
    "validation_error",
    "not_found",
    "conflict",
    "retryable_error",
    "rejected",
    "not_allowed",
    "mismatch",
    ]



class ToolResult(BaseModel):

    """What every tool returns: a fixed status the code can switch on, a message the model can repeat, and the data."""

    status: ToolStatus
    message: str
    data: dict[str, Any] | None = None
    error_code: str | None = None
    retryable: bool = False
    verified: bool | None = None
    block: dict[str, Any] | None = None


def ok(
    message: str,
    data: dict[str, Any] | None = None,
    block: dict[str, Any] | None = None,
    ) -> ToolResult:

    """The tool did what was asked, with a card for the chat when it has one."""

    return ToolResult(status="success", message=message, data=data, block=block)


def card_hint(tool_call_id: str) -> str:

    """Tell the model how to place this result's card in its answer, and not to repeat its numbers."""

    return (
        f"This result has a card the app can draw for the user. To show it, write {{{{card:{tool_call_id}}}}} "
        "on its own line where it should appear in your answer. The card already shows these numbers, "
        "so do not repeat them in a table. Leave it out when the user does not need to see this data."
        )


def checked(
    message: str,
    data: dict[str, Any] | None = None,
    ) -> ToolResult:

    """The write was done and the row read back from the database matches what was asked."""

    return ToolResult(status="success", message=message, data=data, verified=True)


def mismatch(fields: dict[str, dict[str, str]]) -> ToolResult:

    """The row read back did not match what was asked, so the whole save was undone."""

    message = "Not saved: the check after saving found different values, so the change was undone."

    return ToolResult(status="mismatch", message=message, data={"wrong_fields": fields}, error_code="save_mismatch")


def unverified() -> ToolResult:

    """A write tool returned success without reading its row back, so the save was undone."""

    message = "Not saved: this save could not be checked, so the change was undone."

    return ToolResult(status="mismatch", message=message, error_code="not_verified")


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


def retryable(
    message: str,
    error_code: str = "db_unavailable",
    ) -> ToolResult:

    """The database timed out or could not be reached, after every try, so the user can try again later."""

    return ToolResult(status="retryable_error", message=message, error_code=error_code, retryable=True)


def rejected(
    error_code: str,
    message: str,
    ) -> ToolResult:

    """The user did not approve the call, or stopped the reply, so it never ran."""

    return ToolResult(status="rejected", message=message, error_code=error_code)


def not_allowed(tool_name: str) -> ToolResult:

    """The server has no policy for this tool, so it never runs."""

    return ToolResult(status="not_allowed", message=f"{tool_name} is not allowed.", error_code="no_policy")


def over_limit(error_code: str) -> ToolResult:

    """The reply already reached one of its limits, so this call never ran."""

    message = "Not done: this reply reached its limit, so nothing was changed."

    return ToolResult(status="not_allowed", message=message, error_code=error_code)


def repeated_failure(tool_name: str) -> ToolResult:

    """The tool already failed the same way three times in this reply, so it does not run a fourth time."""

    message = (
        f"{tool_name} failed {REPEAT_LIMIT} times in a row with the same error, so it was not run again. "
        "Stop calling it in this reply. Tell the user that this did not work."
        )

    return ToolResult(status="not_allowed", message=message, error_code="repeated_failure")


def tool_failed(tool_name: str) -> ToolResult:

    """The tool broke on its own, so this call did nothing and the rest of the reply can go on."""

    message = f"{tool_name} failed inside the app, so nothing was done. Tell the user it did not work. Do not try it again."

    return ToolResult(status="not_allowed", message=message, error_code="tool_failed")


def bad_arguments(
    tool_name: str,
    errors: list[dict[str, str]],
    ) -> ToolResult:

    """The model called the tool with missing or wrong arguments, so it never ran."""

    problems = "; ".join(f"{error['field']}: {error['problem']}" for error in errors)

    message = f"{tool_name} was not run because of wrong details: {problems}. Fix them and call it again, or ask the user."

    return invalid("invalid_arguments", message, {"errors": errors})


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

    if isinstance(exc, HoldingMissing):
        return ToolResult(status="not_found", message=str(exc), error_code="holding_missing")

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

    """Send the result as JSON to the model without its card, marked error unless it succeeded, with the result kept whole as the artifact."""

    content: str | list[dict[str, str]] = result.model_dump_json(exclude_none=True, exclude={"block"})

    extras = [extra_text] if extra_text is not None else []

    if result.block is not None and result.block.get("type") != "form":
        extras.append(card_hint(tool_call_id))

    if extras:
        content = [{"type": "text", "text": content}, *({"type": "text", "text": text} for text in extras)]

    return ToolMessage(
        content,
        tool_call_id=tool_call_id,
        name=name,
        status="success" if result.status == "success" else "error",
        artifact=result.model_dump(mode="json", exclude_none=True),
        )
