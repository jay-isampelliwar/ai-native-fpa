from typing import NotRequired

from langgraph.graph import MessagesState


class PlannerState(MessagesState):

    """One chat turn: the thread's messages, who is asking, and which thread it is."""

    user_id: int
    conversation_id: str

    conversation_summary: NotRequired[str]
