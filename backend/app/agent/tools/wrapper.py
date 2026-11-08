"""The step every tool call runs through: refuse a tool with no policy or that keeps failing, time each try, retry what is safe, and stamp the name."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.prebuilt.tool_node import ToolCallRequest, ToolInvocationError
from langgraph.types import Command

from app.agent.cancellation import RunCancelled, stop_if_cancelled
from app.agent.tools.limits import RETRYABLE_ERRORS, can_retry, classify, retry_wait, tool_timeout, worth_retrying
from app.agent.tools.policies import policy_for
from app.agent.tools.results import REPEAT_LIMIT, bad_arguments, not_allowed, repeated_failure, to_message, tool_failed
from app.core.config import get_settings
from app.observability.observations import Step, observe_step, update_step


type ToolExecute = Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]]

type FailureSign = tuple[str, ...]

log = logging.getLogger(__name__)

PASS_THROUGH = (RunCancelled, GraphBubbleUp)

GUARD_SUFFIX = "-guard"
ATTEMPT_SUFFIX = ".attempt"

QUIET_STATUSES = ("success", "rejected")
RETRYABLE_STATUS = "retryable_error"
CRASH_CODE = "tool_failed"


def invocation_error(exc: ToolInvocationError) -> str:

    """Turn bad arguments into the JSON result every tool returns, and any other tool crash into a failed result, letting a stop request through."""

    if isinstance(exc, PASS_THROUGH):
        raise exc

    if not isinstance(exc, ToolInvocationError):

        name = str(getattr(exc, "tool_name", "")) or "This tool"

        log.error("tool crashed", exc_info=exc)

        return tool_failed(name).model_dump_json(exclude_none=True)

    raw = exc.filtered_errors if exc.filtered_errors is not None else exc.source.errors()

    errors = [
        {"field": ".".join(str(part) for part in error.get("loc", ())) or "details", "problem": error.get("msg", "invalid")}
        for error in raw
        ]

    return bad_arguments(exc.tool_name, errors).model_dump_json(exclude_none=True)


def this_turn(state: Any) -> list[Any]:

    """The messages since the user's latest message, or none when the state holds no message list."""

    messages = state.get("messages", []) if isinstance(state, dict) else []

    for index in range(len(messages) - 1, -1, -1):

        if isinstance(messages[index], HumanMessage):
            return messages[index + 1:]

    return list(messages)


def failure_sign(message: ToolMessage) -> FailureSign | None:

    """What a failed result said, to compare failures, or None for a success or a call the user turned down."""

    if message.status != "error":
        return None

    text = message.content if isinstance(message.content, str) else str(message.content)

    try:
        result = json.loads(text)

    except ValueError:
        return ("raw", text)

    if not isinstance(result, dict) or result.get("status") == "rejected":
        return None

    return (str(result.get("status")), str(result.get("error_code")), str(result.get("message")))


def keeps_failing(
    state: Any,
    tool_name: str,
    ) -> bool:

    """True when this tool's last few results in this reply all failed with the very same error."""

    results = [message for message in this_turn(state) if isinstance(message, ToolMessage) and message.name == tool_name]

    last = results[-REPEAT_LIMIT:]

    if len(last) < REPEAT_LIMIT:
        return False

    signs = [failure_sign(message) for message in last]

    return None not in signs and len(set(signs)) == 1


def result_fields(message: ToolMessage) -> dict[str, Any]:

    """The JSON result a tool message carries, read from its text or its first text part, or an empty dict when there is none."""

    content = message.content

    if isinstance(content, list) and content and isinstance(content[0], dict):
        content = content[0].get("text", "")

    if not isinstance(content, str):
        return {}

    try:
        result = json.loads(content)

    except ValueError:
        return {}

    return result if isinstance(result, dict) else {}


def outcome_level(
    status: str,
    error_code: str | None,
    ) -> str:

    """The Langfuse level for a call's final answer: plain for a success or a user's no, error for a crash or tries used up, else a warning."""

    if status in QUIET_STATUSES:
        return "DEFAULT"

    if status == RETRYABLE_STATUS or error_code == CRASH_CODE:
        return "ERROR"

    return "WARNING"


def guard_outcome(message: ToolMessage | Command) -> dict[str, Any]:

    """What the guard step records about a call's answer: its status, error code, whether it may be retried, and its level."""

    if not isinstance(message, ToolMessage):
        return {"metadata": {"status": "command"}}

    result = result_fields(message)

    status = str(result.get("status") or ("success" if message.status != "error" else "error"))
    error_code = result.get("error_code")
    level = outcome_level(status, error_code)

    outcome: dict[str, Any] = {
        "metadata": {"status": status, "error_code": error_code, "retryable": bool(result.get("retryable", False))},
        "level": level,
        }

    if level != "DEFAULT":
        outcome["status_message"] = f"{status}: {error_code}"

    return outcome


async def finish_tool_call(
    request: ToolCallRequest,
    execute: ToolExecute,
    ) -> ToolMessage | Command:

    """Stop if the run was asked to, then guard the call inside a guardrail step that records its attempts, status and error code."""

    name = request.tool_call["name"]

    await stop_if_cancelled(request.runtime.context.run_id)

    async with observe_step(get_settings(), f"{name}{GUARD_SUFFIX}", "guardrail", {"tool": name}) as step:

        message = await guard_tool_call(request, execute, step)

        update_step(step, **guard_outcome(message))

    return message


async def guard_tool_call(
    request: ToolCallRequest,
    execute: ToolExecute,
    step: Step | None,
    ) -> ToolMessage | Command:

    """Run one tool call within its time limit, try again on a timeout or outage when safe, turn any other crash into a failed result, and answer."""

    call = request.tool_call
    context = request.runtime.context

    if policy_for(call["name"]) is None:
        return to_message(not_allowed(call["name"]), call["id"], call["name"])

    if keeps_failing(request.state, call["name"]):
        return to_message(repeated_failure(call["name"]), call["id"], call["name"])

    attempts = get_settings().TOOL_RETRY_ATTEMPTS if can_retry(call["name"], context) else 1

    for attempt in range(attempts):

        update_step(step, metadata={"attempts": attempt + 1})

        failure: BaseException | None = None

        async with observe_step(get_settings(), f"{call['name']}{ATTEMPT_SUFFIX}", "span", {"attempt": attempt + 1}) as try_step:

            try:

                async with asyncio.timeout(tool_timeout(context)):
                    message = await execute(request)

            except RETRYABLE_ERRORS as exc:

                update_step(try_step, level="WARNING", status_message=type(exc).__name__)

                failure = exc

            except PASS_THROUGH:
                raise

            except Exception:

                log.exception("tool %s crashed", call["name"])

                update_step(try_step, level="ERROR", status_message=CRASH_CODE)

                return to_message(tool_failed(call["name"]), call["id"], call["name"])

        if failure is not None:

            wait = retry_wait(attempt)

            if attempt + 1 >= attempts or not worth_retrying(context, wait):
                return to_message(classify(failure), call["id"], call["name"])

            await asyncio.sleep(wait)

            continue

        if isinstance(message, ToolMessage):
            message.name = call["name"]

        return message
