"""What one chat turn carries through the graph."""

from typing import NotRequired

from langgraph.graph import MessagesState

from app.agent.budget import Budget

class PlannerState(MessagesState):

    turn_count: NotRequired[int]
    memories: NotRequired[list[str]]
    skip_reply: NotRequired[bool]
    budget: NotRequired[Budget]
