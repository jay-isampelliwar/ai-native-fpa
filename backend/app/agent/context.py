"""What one turn of the agent is given and what it produces, replacing the old skill contracts.

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

``returned`` holds the raw text of every tool result and is filled in by the runtime after the agent
finishes, from the agent's own message list, rather than by each tool. It is what the figure check
compares the reply against, so a total the model added up itself has nowhere to have come from.

Evidence and calculator versions are accumulated with duplicates dropped and first appearance order
kept. Two tools legitimately read the same row - listing SIPs and computing cash flow both touch the
same instructions - and a repeated id makes one record look like two pieces of corroboration.

Nothing here is persisted. The log lives for one turn; what survives is the transcript row, the audit
row and whatever the tools wrote to the database.
"""

from pydantic import BaseModel, Field

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
