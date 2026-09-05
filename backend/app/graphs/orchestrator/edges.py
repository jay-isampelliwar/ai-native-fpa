"""The conditional edges that decide where a request goes next.

These functions are the safety guarantee of the whole design made concrete. A node can
propose anything, but only an edge can move a request forward, and every edge here is
ordinary Python reading ordinary state. No model output selects a destination.

Read them as three one way gates. ``after_routing`` refuses to continue when routing
failed. ``after_permission_check`` refuses to reach a skill when the caller lacks the
scopes. ``route_by_risk`` refuses to reach a write when the skill's own definition says
approval is required and no approval exists yet.

Every refusal branch lands on ``write_audit_record`` rather than jumping to the reply.
A denied request is an outcome worth keeping, and routing it around the audit node would
make the trail show only the requests that succeeded.

``route_by_risk`` trusts the registered ``SkillDefinition``, never the skill's own
returned result, when deciding whether approval is needed. A skill that returns
``status="approved"`` is not believed: approval is a property of the request's history,
recorded by the approval node, not a claim the skill can make about itself.

The Literal return annotations are not decoration. They are the exact node names passed
to ``add_conditional_edges``, so a typo becomes a type error at build time instead of a
KeyError during a user's request.
"""

from typing import Literal

from app.graphs.orchestrator.state import PlannerState


def after_routing(state: PlannerState) -> Literal["load_skill_definition", "write_audit_record"]:

    """Continue only when the router produced a usable skill name, otherwise record the refusal and stop."""

    if state.denial_reason or not state.skill_name:
        return "write_audit_record"

    return "load_skill_definition"


def after_permission_check(state: PlannerState) -> Literal["execute_skill", "write_audit_record"]:

    """Let the request reach a skill only when the caller holds every scope that skill requires."""

    if not state.permission_granted:
        return "write_audit_record"

    return "execute_skill"


def route_by_risk(state: PlannerState) -> Literal["request_approval", "write_audit_record"]:

    """Send an actual proposal to a human, and everything else straight to the audit record."""

    if state.validation_errors:
        return "write_audit_record"

    if state.definition is None or not state.definition.requires_approval:
        return "write_audit_record"

    result = state.result

    if result is None or result.status != "proposed" or not result.pending_approval_id:
        return "write_audit_record"

    return "request_approval"
