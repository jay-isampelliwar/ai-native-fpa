"""The deterministic steps that bracket the agent run, written as plain functions.

Three nodes are left of the seven that used to be here, and the three that remain are the ones that
were never about choosing anything: identify the caller, record what happened, say it.

What went, and why it is worth knowing what is missing. ``validate_skill_result`` checked a skill's
returned status against its registered definition - there are no definitions now, and the property it
protected most (a skill claiming a completed write when its definition required approval) describes a
situation that cannot arise. ``request_approval`` and ``controlled_write`` were the interrupt and the
write behind it; the tools write directly by explicit product decision, so the pause has nothing left
to pause. ``app.agent.tools.writes`` carries the description of that trade.

``authenticate_context`` still runs first and still mints the correlation id everything else is logged
against. In this phase ``local_user`` grants every scope, so it is wiring rather than a decision - but
it is the seam a real credential lands in, and the agent's tools are bound to the context it produces.

``write_audit_record`` sits in front of ``respond`` on every path, including the failure path, so a
request cannot answer a person without leaving a trail. It now records which tools ran and what they
changed rather than which skill was routed to.

``respond`` chooses between what is already in state and writes nothing of its own. The sentence a
person reads was settled in the agent runtime, where the figure check had already had its say; adding
a second model call here could only reword an answer that is already in the planner's own words, and
could only introduce a figure the first one was prevented from inventing.

Nodes return a dict of state updates rather than a mutated ``PlannerState``, so each node's
contribution is explicit and a node that returns nothing has provably changed nothing.

Failure is expressed in state, not by raising. A refusal records a ``denial_reason`` and still reaches
the audit node and still owes the person an explanation, both of which an exception would skip.
"""

from app.agent.context import AgentContext
from app.audit.recorder import recorder
from app.core.config import settings
from app.core.security import local_user, new_correlation_id
from app.graphs.orchestrator.state import PlannerState


def authenticate_context(state: PlannerState) -> dict:

    """Resolve the caller and mint the correlation id, producing the context every tool is bound to."""

    user = local_user(state.user_id)

    context = AgentContext(
        user_id=user.user_id,
        conversation_id=state.conversation_id,
        correlation_id=new_correlation_id(),
        timezone=settings.default_timezone,
        currency=settings.default_currency,
    )

    return {"user": user, "context": context}


async def write_audit_record(state: PlannerState) -> dict:

    """Capture what this turn read, computed and changed, for every outcome including failures."""

    await recorder.record(state)

    return {}


def respond(state: PlannerState) -> dict:

    """Choose the single message the person reads, preferring a refusal reason over an empty answer."""

    if state.denial_reason:
        return {"response": f"I could not do that: {state.denial_reason}"}

    if state.response:
        return {}

    return {"response": "I could not produce an answer for that request."}
