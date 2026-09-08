"""What one turn is given, what it collects while running, and what flows between the nodes.

Three things live here because they are the same subject seen at three moments: the context a turn
starts from, the log it fills in while the tools run, and the state the graph carries between nodes.
They were three files in two packages, which made a reader follow imports to answer one question.

``AgentContext`` is the former ``SkillContext`` under a name that still means something now that there
are no skills. It carries identity and locale and nothing else, and that restriction matters more here
than it did before: every tool is built bound to this context, so a tool physically cannot be asked
about another user. The model never sees a user id and has no parameter to put one in.

``RunLog`` is what a turn reports about itself. It used to carry the structured half of every tool's
output - the tables, charts, evidence ids and calculator versions a skill once returned in a
``SkillResult`` - because a tool may only return text to the model and something had to collect the
rest. That was the backend of the generated interface, and it is deliberately gone for now: the chat
answers in prose, the client renders no blocks from it, and the workspace panel builds its own.

What is left is two lists. ``writes`` records what actually changed, in the tool's own words, so the
sentence a person reads and the change that reached the database describe the same event. ``tools``
records everything that ran, reads included, and keeps repeats - a turn that listed SIPs, updated one
and listed them again did three things, and collapsing that to a set would hide the loop.

Nothing in the log is persisted. It lives for one turn; what survives is the transcript row and
whatever the tools wrote to the database.

``PlannerState`` is what the graph carries. Every node reads from it and writes to it, fields are
optional and start empty, and each node fills in its own slice, so the presence or absence of a field
is itself the record of how far a request travelled.

It is much smaller than it was. It used to carry a routed skill name, that skill's registered
definition, a routing confidence, a permission decision, a validated ``SkillResult`` and an approval
decision - because a turn was a route to one skill, a check on that skill, and possibly a pause for a
human. A turn is now one agent run, so what survives is what the agent produced: the sentence, the
tools it called, what it changed, and the blocks and evidence behind the figures.

One rule keeps this type safe to persist: it holds identifiers and outcomes, never financial records.
This object is checkpointed to PostgreSQL and a fat state becomes a second, stale source of truth.

``writes_performed`` is the field that replaced ``write_outcome``, and it is a list rather than a flag
because one turn can now change several things. It holds each change in the words the person was told,
which is what makes the audit row and the reply describe the same event.

``tools_used`` keeps repeats. A turn that listed SIPs, updated one and listed them again did three
things, and collapsing that to a set would hide the loop.

``new_turn`` exists because the state is checkpointed per conversation and a second message on the
same thread inherits everything the first one left behind. That was not a subtle bug: a run whose
``response`` was already set returned it and stopped, so every message after the first replayed the
first answer. Clearing the whole per turn block is deliberate rather than clearing the one field that
happens to show.

``AgentContext`` is named in the checkpointer's allowlist of types it will deserialise, by module
path. Moving this class means editing ``app.db.checkpointer`` in the same breath, or every existing
checkpoint fails to load.
"""

from pydantic import BaseModel, Field

from app.core.security import AuthenticatedUser


class AgentContext(BaseModel):

    """Per turn identity and locale handed to every tool, deliberately holding no financial data."""

    user_id: int
    conversation_id: str
    correlation_id: str
    timezone: str = "Asia/Kolkata"
    currency: str = "INR"


class RunLog:

    """Records what a turn's tools did, since a tool may only return text to the model."""

    def __init__(self) -> None:

        """Start empty, which is also the state of a turn that answers without calling anything."""

        self.tools: list[str] = []
        self.writes: list[str] = []

    def used(self, name: str) -> None:

        """Note that a tool ran, keeping repeats because calling one twice is worth seeing."""

        self.tools.append(name)

    def wrote(self, detail: str) -> None:

        """Record one change that actually reached the database, in the words the person will read."""

        self.writes.append(detail)


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
        "denial_reason": None,
        "response": None,
    }


class PlannerState(BaseModel):

    """Accumulating state for one request as it moves from authentication through the agent run."""

    user_id: int
    conversation_id: str
    user_message: str

    user: AuthenticatedUser | None = None
    context: AgentContext | None = None

    tools_used: list[str] = Field(default_factory=list)
    writes_performed: list[str] = Field(default_factory=list)

    denial_reason: str | None = None
    response: str | None = None
