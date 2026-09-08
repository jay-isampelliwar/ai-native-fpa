"""What one turn is given, what it collects while running, and what flows between the nodes.

Three things live here because they are the same subject seen at three moments: the context a turn
starts from, the log it fills in while the tools run, and the state the graph carries between nodes.
They were three files in two packages, which made a reader follow imports to answer one question.

``AgentContext`` is the former ``SkillContext`` under a name that still means something now that there
are no skills. It carries identity and locale and nothing else, and that restriction matters more here
than it did before: every tool is built bound to this context, so a tool physically cannot be asked
about another user. The model never sees a user id and has no parameter to put one in.

``RunLog`` is the part that has no predecessor. A skill used to return a ``SkillResult`` carrying its
blocks, evidence and calculator versions, because a skill was one call that produced one answer. A
tool cannot do that - it may only return text to the model - so the structured half of what the tools
produce is collected here as they run, and assembled into the response after the model has finished
talking.

That is why every tool takes a log. It is not a convenience: without it the interface would get the
model's prose and none of the tables, charts or evidence ids underneath it, which is most of what
makes this product answer a question about money rather than chat about one.

``writes`` records what actually changed, in the tool's own words, and it is the field the audit row
and the closing sentence are both built from. Reads are recorded too, under ``tools``, so an audit
row says what a turn looked at as well as what it altered.

``returned`` holds the raw text of every tool result and is filled in by the nodes after the agent
finishes, from the agent's own message list, rather than by each tool. It is what the figure check
compares the reply against, so a total the model added up itself has nowhere to have come from.

Evidence and calculator versions are accumulated with duplicates dropped and first appearance order
kept. Two tools legitimately read the same row - listing SIPs and computing cash flow both touch the
same instructions - and a repeated id makes one record look like two pieces of corroboration.

Nothing in the log is persisted. It lives for one turn; what survives is the transcript row, the audit
row and whatever the tools wrote to the database.

``PlannerState`` is what the graph carries. Every node reads from it and writes to it, fields are
optional and start empty, and each node fills in its own slice, so the presence or absence of a field
is itself the record of how far a request travelled.

It is much smaller than it was. It used to carry a routed skill name, that skill's registered
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

``AgentContext`` is named in the checkpointer's allowlist of types it will deserialise, by module
path. Moving this class means editing ``app.db.checkpointer`` in the same breath, or every existing
checkpoint fails to load.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.core.security import AuthenticatedUser
from app.ui.blocks import Block


class AgentContext(BaseModel):

    """Per turn identity and locale handed to every tool, deliberately holding no financial data."""

    user_id: int
    conversation_id: str
    correlation_id: str
    timezone: str = "Asia/Kolkata"
    currency: str = "INR"


class RunLog:

    """Collects the structured output of a turn's tool calls, since a tool may only return text."""

    def __init__(self) -> None:

        """Start empty, which is also the state of a turn that answers without calling anything."""

        self.tools: list[str] = []
        self.writes: list[str] = []
        self.returned: list[str] = []
        self.blocks: list[Block] = []
        self.spoken: list[str] = []
        self.evidence_ids: list[str] = []
        self.calculator_versions: list[str] = []
        self.assumptions: dict[str, float] = {}

    def used(self, name: str) -> None:

        """Note that a tool ran, keeping repeats because calling one twice is worth seeing."""

        self.tools.append(name)

    def wrote(self, detail: str) -> None:

        """Record one change that actually reached the database, in the words the person will read."""

        self.writes.append(detail)

    def add_blocks(self, blocks: list[Block]) -> None:

        """Keep blocks a tool produced, so the interface renders figures under the model's sentence."""

        self.blocks.extend(blocks)

    def add_evidence(self, identifiers: list[str]) -> None:

        """Record the rows a tool read, dropping ids already seen this turn."""

        for identifier in identifiers:

            if identifier not in self.evidence_ids:
                self.evidence_ids.append(identifier)

    def add_versions(self, versions: list[str]) -> None:

        """Record which calculator produced a figure, so an explanation months later can name it."""

        for version in versions:

            if version not in self.calculator_versions:
                self.calculator_versions.append(version)

    def add_sentence(self, sentence: str) -> None:

        """Keep a tool's own wording, which is what the reply falls back to if the model invents a figure."""

        if sentence:
            self.spoken.append(sentence)

    @property
    def changed_anything(self) -> bool:

        """Report whether this turn altered the database, which the audit row records."""

        return bool(self.writes)


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
