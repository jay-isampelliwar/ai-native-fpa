"""The HTTP shapes of the planner, kept separate from the graph's internal state.

``PlannerState`` is an internal object that grows as a request moves through the graph
and holds things a client has no business seeing - the loaded skill definition, the raw
denial reason, the caller's resolved scopes. These schemas are the deliberately narrow
view of it that crosses the network, so widening the state never accidentally widens the
API.

``MessageRequest`` carries the ``user_id`` directly because Phase 1 has no tokens. That
is the one field to revisit when real authentication arrives: it moves out of the body
and into a verified credential, and nothing else in this module changes.

``conversation_id`` doubles as the LangGraph thread id. Sending the same one continues
the same conversation and, more importantly, is what lets an interrupted request be
resumed - so a client that loses it cannot approve the change it was just shown.

``MessageResponse`` returns evidence ids and calculator versions to the client rather
than keeping them server side. A user is entitled to see which records and which formula
version produced the number they are reading, and an interface that cannot show that
cannot honestly present the answer as verified.

``blocks`` carries the typed UI the frontend renders, and ``response`` stays beside it as the
plain text of the same answer. Neither is derived from the other at this layer - the skill built
both from one set of figures - so a client may render blocks, text, or both without either being
a lossy summary of the other.

A paused run returns an ``approval_card`` block as well as the ``pending_approval`` object. The
block is what gets rendered inline in the conversation; the object is what the client posts back.
Keeping them separate means a client that renders no blocks can still complete an approval.

``ConversationMessageRead`` re-validates the stored blocks through the same union the live response
uses. A transcript that could return a shape the live path cannot would be a second, weaker contract
with the frontend, and the one place it would show up is on a screen nobody looks at until they are
already trying to remember what they were told.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.ui.blocks import Block


class MessageRequest(BaseModel):

    """One user message, with the caller's id supplied directly until real authentication lands."""

    user_id: int
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


class MessageResponse(BaseModel):

    """What the client receives: the answer, and enough about the turn to classify and store it."""

    conversation_id: str
    correlation_id: str | None = None
    skill: str | None = None
    status: str = "answered"
    response: str = ""


class ApprovalRequest(BaseModel):

    """A human's answer to a paused run, tied to the conversation whose state is waiting."""

    user_id: int
    conversation_id: str
    decision: str = Field(pattern="^(approve|reject)$")


class ConversationMessageRead(BaseModel):

    """One recorded turn, returned in the same shape the client was shown when it happened."""

    id: str
    position: int
    role: str
    text: str = ""
    blocks: list[Block] = Field(default_factory=list)
    skill: str | None = None
    status: str | None = None
    correlation_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    calculator_versions: list[str] = Field(default_factory=list)
    created_at: datetime


class ConversationRead(BaseModel):

    """One chat session as it appears in a list: what it was about and when it was last spoken to."""

    id: str
    title: str | None = None
    message_count: int = 0
    created_at: datetime
    last_message_at: datetime


class ConversationDetail(ConversationRead):

    """One chat session together with its turns, which is what reopening a conversation loads."""

    messages: list[ConversationMessageRead] = Field(default_factory=list)
