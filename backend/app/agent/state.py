from typing import NotRequired
from langgraph.graph import MessagesState

class PlannerState(MessagesState):
    
    user_id: int
    conversation_id: str

    conversation_summary: NotRequired[str]
