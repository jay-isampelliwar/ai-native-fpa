"""The recent messages block: which turns still fit, cut only where a person starts speaking."""

from langchain_core.messages import BaseMessage, HumanMessage

from app.agent.agent_config import RECENT_MESSAGES_TOKENS_THRESHOLD
from app.agent.context.tokens import count_messages
from app.agent.state import PlannerState


def turn_starts(messages: list[BaseMessage]) -> list[int]:

    """List the positions where the person speaks, which are the only places the thread may be cut."""

    return [index for index, message in enumerate(messages) if isinstance(message, HumanMessage)]


def cut_point(messages: list[BaseMessage]) -> int:

    """Find the oldest message worth keeping: the first whole turn whose remainder fits the budget."""

    starts = turn_starts(messages)

    if len(starts) < 2:
        return 0

    for start in starts:

        if count_messages(messages[start:]) <= RECENT_MESSAGES_TOKENS_THRESHOLD:
            return start

    return starts[-1]


def recent_messages(state: PlannerState) -> list[BaseMessage]:

    """Take the newest whole turns that fit, so an oversized thread cannot reach the model."""

    messages = state["messages"]

    return messages[cut_point(messages) :]


def stale_messages(state: PlannerState) -> list[BaseMessage]:

    """Take the older turns that no longer fit, which are the ones the summary has to absorb."""

    messages = state["messages"]

    return messages[: cut_point(messages)]
