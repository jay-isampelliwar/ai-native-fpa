"""The single object that flows through the top level graph, one instance per request.

Every node in the orchestrator reads from and writes to a ``PlannerState``. Fields are
optional and start empty on purpose: each node fills in its own slice, so the presence
or absence of a field is itself the record of how far a request travelled. A state with
``definition`` set but ``permission_granted`` still False is a request that was routed
and then refused, and that is exactly what the audit node should see.

Two rules keep this type safe to persist. First, it holds *identifiers and decisions*,
never financial records - ``evidence_ids`` inside ``SkillResult`` point at rows in the
application database rather than copying them, because this object is checkpointed to
PostgreSQL and a fat state becomes a second, stale source of truth. Second, no node may
clear a field an earlier node set; the state only accumulates, so a resumed run after an
approval interrupt sees the same proposal it paused on.

``approval_decision`` stays None until a human answers. ``write_outcome`` stays None
unless a controlled write actually executed, which makes "did anything change?" a field
check rather than an inference.
"""

from typing import Any

from pydantic import BaseModel, Field

from backend.agent_runtime.contracts import SkillContext, SkillDefinition, SkillResult


class PlannerState(BaseModel):

    """Accumulating state for one request as it moves through authenticate, route, execute, approve and audit."""

    user_message: str
    context: SkillContext | None = None
    skill_name: str | None = None
    definition: SkillDefinition | None = None
    permission_granted: bool = False
    denial_reason: str | None = None
    result: SkillResult | None = None
    validation_errors: list[str] = Field(default_factory=list)
    approval_decision: str | None = None
    write_outcome: dict[str, Any] | None = None
    response: str | None = None
