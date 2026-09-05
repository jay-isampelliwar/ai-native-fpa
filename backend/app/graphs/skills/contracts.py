"""The stable contracts every financial skill is written against.

Nothing in this module knows about LangGraph, OpenAI or the database, and that is
deliberate. These four types are the seam that lets the orchestration underneath a
skill change - ReAct agent today, manual subgraph tomorrow - without touching the API,
the audit records or any caller.

``SkillContext`` carries identity and locale only. It must never be widened to hold
balances, transactions or holdings: those are fetched inside a skill through permission
checked tools, so that a leak has to pass an authorization decision first. ``user_id`` is
the integer the client sent, matching ``AuthenticatedUser`` in ``app.core.security``;
nothing here parses it, it is carried through to the repositories unchanged.

``SkillDefinition`` is metadata the graph enforces *around* a skill rather than advice
the skill may follow. ``required_permissions`` gates the request before execution,
``allowed_tools`` is the closed set a skill may bind, and the three maximums are hard
budgets - a skill that exceeds them is stopped, not warned.

Currency defaults to INR and timezone to Asia/Kolkata because every downstream
calculator assumes an India resident; override them per tenant, never per request.

``blocks`` is how a skill describes what should be shown rather than only what should be read.
It is a list of typed UI blocks from ``app.ui.blocks``, and ``message`` remains the plain text
fallback - a client that renders no blocks, a log line, or a future voice surface still gets a
complete answer. The two must agree, because they are two renderings of one result.

``write_tool`` names the controlled write a proposal should execute if approved. A skill names
it; only the orchestrator calls it, and only after an approval. That indirection is what keeps a
skill from being able to write even when it knows exactly what write it wants.

``proposed_changes`` is the before and after the user is shown, in the shape the approval card
renders. It travels with the result so the interrupt payload, the stored approval and the card a
person reads are all the same description of the same change.

``calculator_versions`` is as load bearing as ``evidence_ids``. Evidence says which rows
a conclusion came from; the calculator version says which arithmetic turned them into a
number. A plan explained months later needs both, so any skill quoting a computed figure
records the version that produced it.

``quotes_figures`` exists for the one skill that answers about the service rather than about the
records. The validator requires evidence identifiers behind any answered result, because a figure
nobody can trace is the failure this whole design prevents. A skill that quotes no figure - one that
describes what the planner can do - would be rejected for lacking evidence it never claimed to have.
The flag defaults to True, so a skill has to say so explicitly and a reviewer sees it in the
definition rather than discovering it in a validator exemption.

``SkillResult.status`` is drawn from ``SKILL_STATUSES`` and each value is a claim the
validator checks rather than trusts. ``proposed`` means a change was described but not
made and is the only status a skill requiring approval may return. ``completed`` asserts
a write already happened, which is legitimate only from a skill whose definition permits
it - a skill that returns ``completed`` while ``requires_approval`` is True has skipped
the human, and the validator treats that as a failed run.
"""

from typing import Protocol

from pydantic import BaseModel, Field

from app.ui.blocks import Block

SKILL_STATUSES = frozenset({"answered", "proposed", "completed", "refused", "failed"})


class SkillRequest(BaseModel):

    """The generic request handed to a skill, holding the user's words and nothing the skill did not ask for."""

    message: str


class SkillContext(BaseModel):

    """Per request identity and locale handed to a skill, deliberately holding no financial data."""

    user_id: int
    conversation_id: str
    correlation_id: str
    timezone: str = "Asia/Kolkata"
    currency: str = "INR"


class SkillResult(BaseModel):

    """What a skill returns: an answer plus the evidence IDs and assumptions it rests on."""

    status: str
    message: str
    blocks: list[Block] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    calculator_versions: list[str] = Field(default_factory=list)
    assumptions: dict[str, float] = Field(default_factory=dict)
    pending_approval_id: str | None = None
    write_tool: str | None = None
    proposed_changes: list[dict] = Field(default_factory=list)


class SkillDefinition(BaseModel):

    """Registry metadata the top level graph enforces before and after a skill runs."""

    name: str
    version: str
    description: str
    risk_level: str
    required_permissions: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    read_only: bool = True
    requires_approval: bool = False
    quotes_figures: bool = True
    maximum_model_calls: int = 4
    maximum_tool_calls: int = 8
    timeout_seconds: int = 30


class FinancialSkill(Protocol):

    """The only interface the orchestrator knows about, so any skill implementation is swappable."""

    name: str
    version: str

    async def execute(
        self,
        request: BaseModel,
        context: SkillContext,
        ) -> SkillResult: ...
