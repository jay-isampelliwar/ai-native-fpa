"""The single object that flows through the top level graph, one instance per request.

Every node reads from and writes to a ``PlannerState``. Fields are optional and start empty on
purpose: each node fills in its own slice, so the presence or absence of a field is itself the record
of how far a request travelled.

This is much smaller than it was. It used to carry a routed skill name, that skill's registered
definition, a routing confidence, a permission decision, a validated ``SkillResult`` and an approval
decision - because a turn was a route to one skill, a check on that skill, and possibly a pause for a
human. A turn is now one agent run, so what survives is what the agent produced: the sentence, the
tools it called, what it changed, and the blocks and evidence behind the figures.

Two rules keep this type safe to persist. First, it holds identifiers and outcomes, never financial
records - ``evidence_ids`` point at rows in the application database rather than copying them, because
this object is checkpointed to PostgreSQL and a fat state becomes a second, stale source of truth.
Second, nodes only add; nothing clears a field an earlier node set.

``writes_performed`` is the field that replaced ``write_outcome``, and it is a list rather than a flag
because one turn can now change several things. It holds each change in the words the person was told,
which is what makes the audit row and the reply describe the same event.

``tools_used`` keeps repeats. A turn that listed SIPs, updated one and listed them again did three
things, and collapsing that to a set would hide the loop.

``new_turn`` exists because the state is checkpointed per conversation and a second message on the
same thread inherits everything the first one left behind. That was not a subtle bug: a run whose
``response`` was already set returned it and stopped, so every message after the first replayed the
first answer. Clearing the whole per turn block is deliberate rather than clearing the one field that
showed - stale blocks render last turn's tables under this turn's sentence.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.agent.context import AgentContext
from app.core.security import AuthenticatedUser
from app.ui.blocks import Block


def new_turn(user_id: int, conversation_id: str, message: str) -> dict:

    """Build the state one message starts from, clearing everything the previous turn on this thread left."""

    return {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "user_message": message,
        "user": None,
        "context": None,
        "tools_used": [],
        "writes_performed": [],
        "blocks": [],
        "evidence_ids": [],
        "calculator_versions": [],
        "assumptions": {},
        "denial_reason": None,
        "response": None,
    }


class PlannerState(BaseModel):

    """Accumulating state for one request as it moves through authenticate, agent, audit and respond."""

    user_id: int
    conversation_id: str
    user_message: str

    user: AuthenticatedUser | None = None
    context: AgentContext | None = None

    tools_used: list[str] = Field(default_factory=list)
    writes_performed: list[str] = Field(default_factory=list)

    blocks: list[Block] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    calculator_versions: list[str] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)

    denial_reason: str | None = None
    response: str | None = None
