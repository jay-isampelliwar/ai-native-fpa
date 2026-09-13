"""Shrinking the thread back inside its budget after the answer has gone out."""

from langchain_core.messages import RemoveMessage

from app.agent.context.messages import stale_messages
from app.agent.context.structured_state import trim_structured_state
from app.agent.context.summary import rewrite_summary
from app.agent.state import PlannerState


def removals(state: PlannerState) -> list[RemoveMessage]:

    """Name the older messages to delete from the thread, skipping any the checkpointer never gave an id."""

    return [RemoveMessage(id=message.id) for message in stale_messages(state) if message.id]


async def compact_context(state: PlannerState) -> dict:

    """Trim the records and fold the older turns into the memory, touching nothing that already fits."""

    updates: dict = trim_structured_state(state)

    stale = stale_messages(state)

    if not stale:
        return updates

    updates["conversation_summary"] = await rewrite_summary(state.get("conversation_summary", ""), stale)

    updates["messages"] = removals(state)

    return updates
