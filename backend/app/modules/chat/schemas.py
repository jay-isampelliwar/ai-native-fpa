"""Request bodies for the chat route."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):

    """One user message sent to the planner agent."""

    message: str = Field(min_length=1)
