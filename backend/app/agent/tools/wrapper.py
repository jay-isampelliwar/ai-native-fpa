"""The step every tool call runs through: refuse a tool with no policy, time each try, retry what is safe, and stamp the name."""

import asyncio
from collections.abc import Awaitable, Callable

from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from app.agent.cancellation import stop_if_cancelled
from app.agent.tools.limits import RETRYABLE_ERRORS, can_retry, classify, retry_wait, tool_timeout, worth_retrying
from app.agent.tools.policies import policy_for
from app.agent.tools.results import not_allowed, to_message
from app.core.config import get_settings


type ToolExecute = Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]]


async def finish_tool_call(
    request: ToolCallRequest,
    execute: ToolExecute,
    ) -> ToolMessage | Command:

    """Stop if the run was asked to, then run one tool call within its time limit, try again on a timeout or outage when safe, and answer with its result."""

    call = request.tool_call
    context = request.runtime.context

    await stop_if_cancelled(context.run_id)

    if policy_for(call["name"]) is None:
        return to_message(not_allowed(call["name"]), call["id"], call["name"])

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

        if isinstance(message, ToolMessage):
            message.name = call["name"]

        return message
