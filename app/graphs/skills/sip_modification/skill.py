"""The SIP modification skill, the only registered skill whose result can lead to a write.

It returns ``status="proposed"`` and never ``completed``. The distinction is enforced by the
orchestrator's validator, which rejects a completed status from any skill whose definition
requires approval - so a future change here that tried to shortcut the approval would fail its own
contract rather than quietly working.

``write_tool`` names the function the orchestrator will call after approval. The skill knows which
write it wants and still cannot perform it: naming and calling are separated so that "a skill
cannot write" is a property of the call graph rather than of anyone's discipline.

``pending_approval_id`` points at a row that already exists by the time this returns. The proposal
is durable before the graph pauses, so a restart during the user's deliberation loses the
conversation but not the proposal.

A refusal here is a refusal to propose, not a failed run. An unreadable amount or an absent SIP
means the system worked and the answer is no, which is why those return ``refused`` rather than
``failed``.
"""

from app.graphs.skills.contracts import SkillContext, SkillRequest, SkillResult
from app.graphs.skills.sip_modification.definition import DEFINITION
from app.graphs.skills.sip_modification.graph import sip_modification_graph


class SipModificationSkill:

    """Proposes a change to a standing instruction and stops, leaving the write to the approval path."""

    name = DEFINITION.name
    version = DEFINITION.version

    async def execute(
        self,
        request: SkillRequest,
        context: SkillContext,
        ) -> SkillResult:

        """Build a durable proposal for the requested change and return it for a human to approve."""

        state = await sip_modification_graph.ainvoke(
            {
                "user_id": context.user_id,
                "conversation_id": context.conversation_id,
                "correlation_id": context.correlation_id,
                "message": request.message,
            }
        )

        if state.get("failure_reason"):
            return SkillResult(
                status="refused",
                message=f"I could not propose that change: {state['failure_reason']}.",
                evidence_ids=state.get("evidence_ids", []),
            )

        if not state.get("approval_id"):
            return SkillResult(
                status="failed",
                message="I could not prepare that change for approval.",
                evidence_ids=state.get("evidence_ids", []),
            )

        return SkillResult(
            status="proposed",
            message=state["answer"],
            blocks=state.get("blocks", []),
            evidence_ids=state.get("evidence_ids", []),
            calculator_versions=state.get("calculator_versions", []),
            pending_approval_id=state["approval_id"],
            write_tool="update_sip_instruction",
            proposed_changes=state.get("proposed_changes", []),
        )
