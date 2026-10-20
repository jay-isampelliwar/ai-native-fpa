"""Turning saved memories into short plain lines the chat agent reads in its system prompt."""

from typing import Any

from app.db.models import MemoryItem


NAMESPACE_LABELS = {
    "investment_preferences": "Investment",
    "communication_preferences": "Communication",
    "financial_attitudes": "Money attitude",
    "life_events": "Life event",
    "past_decisions": "Past decision",
    }

STANCE_VERBS = {"avoid": "avoids", "prefer": "prefers"}

MEMORY_HEADING = "## What you remember about the user"


def humanize(name: str) -> str:

    """Turn a snake_case name into plain words."""

    return name.replace("_", " ").strip()


def render_value(value: Any) -> str:

    """Write one content value as text, joining lists and small objects."""

    if isinstance(value, list):
        return ", ".join(str(item) for item in value)

    if isinstance(value, dict):
        return "; ".join(f"{humanize(key)}: {render_value(item)}" for key, item in value.items())

    return str(value)


def describe_memory(memory: MemoryItem) -> str:

    """Write one memory as a labelled line, such as "Investment: avoids sectors: tobacco"."""

    label = NAMESPACE_LABELS.get(memory.namespace, humanize(memory.namespace).capitalize())
    verb = STANCE_VERBS.get(memory.content.get("stance"))

    details = "; ".join(
        f"{humanize(key)}: {render_value(value)}"
        for key, value in memory.content.items()
        if key != "stance"
        )

    if verb:
        return f"{label}: {verb} {details}"

    subject = humanize(memory.memory_key or "")

    if not details:
        return f"{label}: {subject}"

    if not subject:
        return f"{label}: {details}"

    return f"{label}: {subject} - {details}"


def describe_memories(lines: list[str]) -> str:

    """Write the memory system message under its own heading, or say there is nothing remembered yet."""

    if not lines:
        return f"{MEMORY_HEADING}\nNothing yet."

    body = "\n".join(f"- {line}" for line in lines)

    return f"{MEMORY_HEADING}\nThese come from the user's past chats.\n{body}"
