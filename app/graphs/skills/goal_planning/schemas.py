"""The state that flows through the goal planning subgraph, one instance per question.

This is a second, smaller ``PlannerState`` living entirely inside one skill. The orchestrator's
state carries a request through routing, permissions and approval; this one carries a question
through the four steps of a projection. Keeping them separate means the top level graph has no
idea how goal planning works internally, which is what makes the skill replaceable.

Fields accumulate and are never cleared, exactly as in the top level state. A node that could
not do its job records why in ``failure_reason`` and leaves the fields below it empty, so the
final node can tell the difference between "no goal was found" and "the projection returned
zero".

``evidence_ids`` is built up as records are read rather than assembled at the end. By the time
the answer is composed, three nodes have touched different tables, and reconstructing which
rows contributed would mean re-reading them.

Nothing here holds a model message list. This subgraph makes no model call, so there is no
conversation to track - the question arrives as a string and leaves as a paragraph.
"""

from decimal import Decimal

from pydantic import BaseModel, Field

from app.calculations.cashflow.v1 import CashflowResult
from app.calculations.goals.v1 import GoalProjection
from app.repositories.goals_repository import GoalSnapshot
from app.ui.blocks import Block


class GoalPlanningState(BaseModel):

    """Accumulating state for one goal question as it moves through resolve, read, project and compose."""

    model_config = {"arbitrary_types_allowed": True}

    user_id: int
    message: str

    snapshot: GoalSnapshot | None = None
    cashflow: CashflowResult | None = None
    projection: GoalProjection | None = None

    surplus_available: Decimal | None = None
    affordable: bool | None = None

    evidence_ids: list[str] = Field(default_factory=list)
    calculator_versions: list[str] = Field(default_factory=list)
    assumptions: dict[str, float] = Field(default_factory=dict)

    failure_reason: str | None = None
    answer: str | None = None
    blocks: list[Block] = Field(default_factory=list)
