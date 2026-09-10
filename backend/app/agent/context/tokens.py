"""Counting tokens locally, so a budget check costs nothing and needs no API call."""

import tiktoken
from langchain_core.messages import BaseMessage

TOKEN_ENCODING = "o200k_base"

MESSAGE_OVERHEAD_TOKENS = 4

_encoding: tiktoken.Encoding | None = None


def count_text(text: str) -> int:

    """Count the tokens in one string, loading the encoder on first use and reusing it after."""

    global _encoding

    if not text:
        return 0

    if _encoding is None:
        _encoding = tiktoken.get_encoding(TOKEN_ENCODING)

    return len(_encoding.encode(text, disallowed_special=()))


def message_text(message: BaseMessage) -> str:

    """Flatten one message into the text that will be billed, tool calls and content blocks included."""

    content = getattr(message, "content", "")

    parts: list[str] = []

    if isinstance(content, str):
        parts.append(content)

    elif isinstance(content, list):

        for block in content:

            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))

            else:
                parts.append(str(block))

    for call in getattr(message, "tool_calls", None) or []:

        parts.append(str(call.get("name", "")))

        parts.append(str(call.get("args", "")))

    return "\n".join(part for part in parts if part)


def count_message(message: BaseMessage) -> int:

    """Count one message, adding the fixed cost every message carries for its role and framing."""

    return count_text(message_text(message)) + MESSAGE_OVERHEAD_TOKENS


def count_messages(messages: list[BaseMessage]) -> int:

    """Count a whole thread, which is what the recent messages budget is measured against."""

    return sum(count_message(message) for message in messages)
