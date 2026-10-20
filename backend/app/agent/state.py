"""What one chat turn carries through the graph."""

from typing import NotRequired

from langgraph.graph import MessagesState

class PlannerState(MessagesState):

    turn_count: NotRequired[int]
    memories: NotRequired[list[str]]
