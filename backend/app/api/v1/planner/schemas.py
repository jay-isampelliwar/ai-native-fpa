"""The HTTP shapes of the chat, kept separate from the graph's state.

There are two shapes left because there is one endpoint left. ``PlannerState`` is an internal object
- the message list, the thread id, the running summary - and these schemas are the narrow view of it
that crosses the network, so widening the state never accidentally widens the API.

``MessageRequest`` carries the ``user_id`` directly because this phase has no tokens. That is the one
field to revisit when real authentication arrives: it moves out of the body and into a verified
credential, and nothing else in this module changes.

``conversation_id`` doubles as the LangGraph thread id. Sending the same one continues the same
conversation, because the checkpointer keyed by that id is what remembers the earlier messages. A
client that loses it starts a fresh chat rather than resuming one.

``MessageResponse`` is what the closing ``done`` event carries, and it holds only the finished text.
The fields that used to sit beside it - blocks, evidence ids, calculator versions, the skill name,
the approval a run was paused on - described a planner that routed to skills and wrote records. None
of that exists right now, so none of it is promised here; each one comes back with the feature that
needs it.
"""

from pydantic import BaseModel, Field


class MessageRequest(BaseModel):

    """One user message, with the caller's id supplied directly until real authentication lands."""

    user_id: int
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


class MessageResponse(BaseModel):

    """What the closing event carries: the thread this turn belongs to and the finished answer."""

    conversation_id: str
    response: str = ""
