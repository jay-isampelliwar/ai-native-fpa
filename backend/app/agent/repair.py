"""Fixing a history left broken by a stopped turn: every tool call the model asked for gets a tool reply."""

from collections.abc import Sequence

from langchain_core.messages import AIMessage, AnyMessage, ToolCall, ToolMessage

from app.agent.tools.results import retryable, to_message


INTERRUPTED = "interrupted"

INTERRUPTED_TEXT = (
    "This step was stopped before it finished, so it may or may not have run. "
    "Check with list_records before doing it again."
    )


def stopped_message(call: ToolCall) -> ToolMessage:

    """The tool reply for a call that was cut off, saying it may or may not have run."""

    return to_message(retryable(INTERRUPTED_TEXT, INTERRUPTED), call["id"], call["name"])


def repaired_history(messages: Sequence[AnyMessage]) -> list[AnyMessage] | None:

    """The history with a stopped reply added after each tool call that has none, or None when nothing is missing."""

    answered = {message.tool_call_id for message in messages if isinstance(message, ToolMessage)}

    fixed: list[AnyMessage] = []
    missing: list[ToolMessage] = []

    for message in messages:

        if missing and not isinstance(message, ToolMessage):

            fixed.extend(missing)

            missing = []

        fixed.append(message)

        if isinstance(message, AIMessage):
            missing = [stopped_message(call) for call in message.tool_calls if call["id"] not in answered]

    fixed.extend(missing)

    if len(fixed) == len(messages):
        return None

    return fixed
