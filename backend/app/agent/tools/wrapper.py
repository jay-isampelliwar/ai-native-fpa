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


type ToolExecute = Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]]

type FailureSign = tuple[str, ...]

log = logging.getLogger(__name__)

PASS_THROUGH = (RunCancelled, GraphBubbleUp)


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


async def finish_tool_call(
    request: ToolCallRequest,
    execute: ToolExecute,
    ) -> ToolMessage | Command:

    """Stop if the run was asked to, then run one tool call within its time limit, try again on a timeout or outage when safe, turn any other crash into a failed result, and answer."""

    call = request.tool_call
    context = request.runtime.context

    await stop_if_cancelled(context.run_id)

    if policy_for(call["name"]) is None:
        return to_message(not_allowed(call["name"]), call["id"], call["name"])

    if keeps_failing(request.state, call["name"]):
        return to_message(repeated_failure(call["name"]), call["id"], call["name"])

    attempts = get_settings().TOOL_RETRY_ATTEMPTS if can_retry(call["name"], context) else 1

    for attempt in range(attempts):

        try:

            async with asyncio.timeout(tool_timeout(context)):
                message = await execute(request)

        except RETRYABLE_ERRORS as exc:

            wait = retry_wait(attempt)

            if attempt + 1 >= attempts or not worth_retrying(context, wait):
                return to_message(classify(exc), call["id"], call["name"])

            await asyncio.sleep(wait)

            continue

        except PASS_THROUGH:
            raise

        except Exception:

            log.exception("tool %s crashed", call["name"])

            return to_message(tool_failed(call["name"]), call["id"], call["name"])

        if isinstance(message, ToolMessage):
            message.name = call["name"]

        return message
