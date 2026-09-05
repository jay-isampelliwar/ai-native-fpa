"""The deterministic gates of the top level graph, written as plain functions.

Every node here is ordinary Python. No model is called, no tool is invoked and no
network request is made, which is what makes them trustworthy: their behaviour cannot
change because a prompt changed, a model was upgraded or a bank statement contained
instructions dressed up as a transaction description.

Nodes return a dict of state updates rather than a mutated ``PlannerState``. LangGraph
merges that dict into the state, so each node's contribution is explicit and a node that
returns nothing has provably changed nothing.

Failure is expressed in state, not by raising. ``load_skill_definition`` and
``check_permissions`` both record a ``denial_reason`` and leave ``permission_granted``
False, because a refusal still has to reach the audit node and still owes the user an
explanation - an exception thrown mid graph skips both.

The ordering matters and is enforced by the edges, not by convention:
``authenticate_context`` mints the correlation id everything else is logged against,
``load_skill_definition`` converts the router's untrusted string into real policy
metadata, and only then does ``check_permissions`` have a concrete list of required
scopes to test the caller against.

``execute_skill`` is the one node that hands control to skill code, and it is wrapped
rather than trusted: the skill's own registered timeout bounds it, and any exception it
raises is caught and turned into a failed result instead of escaping the graph. A crash
inside a skill must still reach the audit node.

``validate_skill_result`` runs immediately afterwards and checks the result against the
definition rather than against itself. Its most important check is the one that catches
a skill claiming ``completed`` when its definition requires approval, because that is
what an unapproved write looks like from the outside.

It also checks the UI blocks, and that check is not cosmetic. A block citing a row the skill
never read is a figure a user can tap and be shown evidence that does not support it, which is
worse than showing no evidence at all. Every block's evidence must be a subset of the result's,
so a block cannot introduce provenance from nowhere.

``request_approval`` is the only node that stops. ``interrupt`` persists the whole state
to the checkpointer and returns control to the caller, so the pending change survives a
closed browser, a restarted process and a deploy. It resumes with whatever the human
sent back, and nothing after it runs until they answer.

``controlled_write`` executes the approved change through a named tool from
``app.tools.controlled_write``. It re-authorises before doing so, because scopes can change
while a proposal waits, and it records the outcome in state so the audit node sees what was
actually applied rather than what was intended.
"""

import asyncio

from langgraph.types import interrupt

from app.approvals.store import approval_store
from app.audit.recorder import recorder
from app.core.config import settings
from app.models.finance import ApprovalStatus
from app.tools.controlled_write.writes import WRITE_TOOLS
from app.core.security import authorize, local_user, new_correlation_id
from app.graphs.orchestrator.state import PlannerState
from app.graphs.skills.contracts import SKILL_STATUSES, SkillContext, SkillRequest, SkillResult
from app.graphs.skills.registry import SkillNotFoundError, registry
from app.ui.blocks import BLOCK_TYPES


def authenticate_context(state: PlannerState) -> dict:

    """Resolve the caller and mint the correlation id, producing the context every later node depends on."""

    user = local_user(state.user_id)

    context = SkillContext(
        user_id=user.user_id,
        conversation_id=state.conversation_id,
        correlation_id=new_correlation_id(),
        timezone=settings.default_timezone,
        currency=settings.default_currency,
    )

    return {"user": user, "context": context}


def load_skill_definition(state: PlannerState) -> dict:

    """Turn the routed skill name into registered policy metadata, or record why no skill could be loaded."""

    if not state.skill_name:
        return {"denial_reason": "no skill was selected for this request"}

    try:
        definition, _ = registry.resolve(state.skill_name)

    except SkillNotFoundError as exc:
        return {"denial_reason": str(exc)}

    return {"definition": definition}


def check_permissions(state: PlannerState) -> dict:

    """Test the caller's scopes against the loaded skill's requirements, recording the decision either way."""

    if state.user is None or state.definition is None:
        return {
            "permission_granted": False,
            "denial_reason": state.denial_reason or "permissions cannot be checked before a skill is loaded",
        }

    decision = authorize(state.user, state.definition.required_permissions)

    if not decision.granted:
        return {"permission_granted": False, "denial_reason": decision.reason}

    return {"permission_granted": True}


async def execute_skill(state: PlannerState) -> dict:

    """Run the resolved skill inside its registered timeout, turning any failure into a recordable result."""

    if state.context is None or state.definition is None:
        return {"result": SkillResult(status="failed", message="skill execution was reached without a loaded skill")}

    _, skill = registry.resolve(state.definition.name, state.definition.version)

    request = SkillRequest(message=state.user_message)

    try:
        async with asyncio.timeout(state.definition.timeout_seconds):
            result = await skill.execute(request, state.context)

    except TimeoutError:
        return {"result": SkillResult(status="failed", message="the skill exceeded its time budget")}

    except Exception as exc:
        return {"result": SkillResult(status="failed", message=f"the skill failed: {type(exc).__name__}")}

    return {"result": result}


def validate_skill_result(state: PlannerState) -> dict:

    """Check the skill's result against its registered definition, collecting every violation found."""

    result = state.result
    definition = state.definition

    if result is None or definition is None:
        return {"validation_errors": ["the skill returned no result"]}

    errors: list[str] = []

    if result.status not in SKILL_STATUSES:
        errors.append(f"unknown result status {result.status!r}")

    if definition.requires_approval and result.status == "completed":
        errors.append("the skill reported a completed write although its definition requires approval")

    if definition.read_only and result.pending_approval_id is not None:
        errors.append("a read only skill proposed an action requiring approval")

    if definition.quotes_figures and result.status in {"answered", "proposed"} and not result.evidence_ids:
        errors.append("a material conclusion was returned without evidence identifiers")

    errors.extend(validate_blocks(result))

    return {"validation_errors": errors}


def validate_blocks(result: SkillResult) -> list[str]:

    """Check that no block shows a figure traced to evidence the skill did not actually read."""

    if not result.blocks:
        return []

    known_evidence = set(result.evidence_ids)

    errors: list[str] = []

    for block in result.blocks:

        if block.type not in BLOCK_TYPES:
            errors.append(f"unknown block type {block.type!r}")

        unsupported = sorted(set(block.evidence_ids) - known_evidence)

        if unsupported:
            errors.append(
                f"block {block.type!r} cites evidence the skill did not read: {', '.join(unsupported)}"
            )

    return errors


def request_approval(state: PlannerState) -> dict:

    """Pause the whole graph until a human answers, persisting the proposed change while it waits."""

    result = state.result

    decision = interrupt(
        {
            "skill": state.skill_name,
            "title": result.message if result else "",
            "message": result.message if result else "",
            "changes": result.proposed_changes if result else [],
            "approval_id": result.pending_approval_id if result else None,
            "assumptions": result.assumptions if result else {},
            "evidence_ids": result.evidence_ids if result else [],
            "expires_in_seconds": settings.approval_expiry_seconds,
        }
    )

    return {"approval_decision": decision if isinstance(decision, str) else "reject"}


async def controlled_write(state: PlannerState) -> dict:

    """Execute the approved change through a named write tool, re-checking permission before it runs."""

    if state.approval_decision != "approve":
        await approval_store.decide(state.result.pending_approval_id, state.user_id, "reject") if (
            state.result and state.result.pending_approval_id
        ) else None

        return {"response": "Nothing was changed because the request was not approved."}

    result = state.result

    if result is None or not result.pending_approval_id or not result.write_tool:
        return {"response": "There was nothing to apply."}

    approval = await approval_store.decide(result.pending_approval_id, state.user_id, "approve")

    if approval is None:
        return {"response": "That proposal could not be found, so nothing was changed."}

    if approval.status != ApprovalStatus.APPROVED:
        return {"response": f"That proposal is {approval.status.value}, so nothing was changed."}

    tool = WRITE_TOOLS.get(result.write_tool)

    if tool is None:
        return {"response": "That change cannot be applied by this system."}

    outcome = await tool(state.user, approval)

    return {
        "write_outcome": outcome.model_dump(),
        "response": outcome.detail if outcome.status == "completed" else f"No change was made: {outcome.detail}.",
    }


async def write_audit_record(state: PlannerState) -> dict:

    """Capture how this request was routed, decided and completed, for every outcome including refusals."""

    await recorder.record(state)

    return {}


def respond(state: PlannerState) -> dict:

    """Choose the single message the user reads, preferring a refusal reason over a skill answer."""

    if state.response:
        return {}

    if state.denial_reason:
        return {"response": f"I could not do that: {state.denial_reason}"}

    if state.validation_errors:
        return {"response": "I could not verify that answer, so I am not showing it."}

    if state.result:
        return {"response": state.result.message}

    return {"response": "I could not produce an answer for that request."}
