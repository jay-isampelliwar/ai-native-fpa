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
"""

from pydantic import BaseModel, Field

from app.ui.blocks import Block


class MessageRequest(BaseModel):

    """One user message, with the caller's id supplied directly until real authentication lands."""

    user_id: int
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


class PendingApproval(BaseModel):

    """The proposed change a paused run is waiting on, shown to the user before anything is written."""

    conversation_id: str
    skill: str | None = None
    summary: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    expires_in_seconds: int = 0


class MessageResponse(BaseModel):

    """What the client receives: the answer, its provenance, and any approval the run is waiting on."""

    conversation_id: str
    correlation_id: str | None = None
    skill: str | None = None
    status: str = "answered"
    response: str = ""
    blocks: list[Block] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    calculator_versions: list[str] = Field(default_factory=list)
    pending_approval: PendingApproval | None = None


class ApprovalRequest(BaseModel):

    """A human's answer to a paused run, tied to the conversation whose state is waiting."""

    user_id: int
    conversation_id: str
    decision: str = Field(pattern="^(approve|reject)$")
