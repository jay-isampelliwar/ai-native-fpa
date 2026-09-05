"""Registration of every skill the planner is allowed to route to, in one explicit list.

The registry is deliberately empty until this module runs. There is no plugin discovery,
no directory scan and no import by name, because any of those would make the reachable
skill set depend on what happens to be on disk. Here it depends on what is written in
``register_skills``, which is a file a reviewer can read in ten seconds and a diff can
show changing.

Registration is also where a skill's definition and its implementation are bound
together. Neither is usable alone: the definition without code cannot run, and the code
without a definition has no permissions, budgets or approval requirement, so the
orchestrator would have nothing to enforce. Pairing them at exactly one point means a
skill can never be reachable while its policy is missing.

The ``enabled`` flag is the rollback switch. A version that turns out to be wrong is
disabled rather than deleted: it stops being routable immediately, but old audit records
still resolve against it and the previous version can be re-enabled without a deploy.

Six skills are registered in three different shapes. The cash flow summary is deterministic end
to end, the expense investigation runs an agent loop, and goal planning and SIP modification are
manual subgraphs. They satisfy one contract and the orchestrator treats them identically.

``orientation`` is the odd one and is registered first because everything else assumes it. It answers
about the planner rather than about the records, and it is what the router falls back to when its
confidence is below the floor - so a request that fits no financial skill gets an answer describing
what the planner can do, rather than the closest skill's refusal.

Four are read only. ``sip_modification`` and ``record_capture`` are the exceptions and the reason
the approval machinery exists: they are the only registered skills whose results can reach a
controlled write, and both reach it by proposing rather than by writing. ``record_capture`` is what
lets a person give the planner a figure in conversation without the conversation being able to store
it - the sentence becomes a card, and the card becomes a record only when they press Add.

Call ``register_skills`` once during application startup, before the graph is compiled.
Calling it twice is harmless, since registration is keyed by name and version.
"""

from app.graphs.skills.cashflow_summary.definition import DEFINITION as CASHFLOW_SUMMARY
from app.graphs.skills.cashflow_summary.skill import CashflowSummarySkill
from app.graphs.skills.expense_investigation.agent import ExpenseInvestigationSkill
from app.graphs.skills.expense_investigation.definition import DEFINITION as EXPENSE_INVESTIGATION
from app.graphs.skills.goal_planning.definition import DEFINITION as GOAL_PLANNING
from app.graphs.skills.goal_planning.skill import GoalPlanningSkill
from app.graphs.skills.orientation.definition import DEFINITION as ORIENTATION
from app.graphs.skills.orientation.skill import OrientationSkill
from app.graphs.skills.record_capture.definition import DEFINITION as RECORD_CAPTURE
from app.graphs.skills.record_capture.skill import RecordCaptureSkill
from app.graphs.skills.sip_modification.definition import DEFINITION as SIP_MODIFICATION
from app.graphs.skills.sip_modification.skill import SipModificationSkill
from app.graphs.skills.registry import SkillRegistry, registry


def register_skills(into: SkillRegistry | None = None) -> SkillRegistry:

    """Bind every approved skill definition to its implementation, returning the populated registry."""

    target = into or registry

    target.register(ORIENTATION, OrientationSkill(), enabled=True)
    target.register(RECORD_CAPTURE, RecordCaptureSkill(), enabled=True)
    target.register(CASHFLOW_SUMMARY, CashflowSummarySkill(), enabled=True)
    target.register(EXPENSE_INVESTIGATION, ExpenseInvestigationSkill(), enabled=True)
    target.register(GOAL_PLANNING, GoalPlanningSkill(), enabled=True)
    target.register(SIP_MODIFICATION, SipModificationSkill(), enabled=True)

    return target
