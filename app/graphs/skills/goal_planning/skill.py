"""The goal planning skill, wrapping its subgraph behind the same contract every skill satisfies.

From the orchestrator's point of view this is indistinguishable from the deterministic cash flow
summary and from the ReAct investigation. All three expose ``name``, ``version`` and ``execute``,
and the top level graph checks permissions, validates results and audits them identically. That
uniformity is the claim the skill design makes, and this is the third and most different shape
proving it.

The subgraph's state is translated into a ``SkillResult`` here rather than being returned. The
orchestrator has no business knowing that this skill has a graph inside it, let alone what its
state looks like - swapping this for a single function later must not change anything upstream.

``status`` distinguishes a refusal from a failure. No goals set up is a refusal: the system
worked and the answer is that there is nothing to project. A missing projection after a goal was
resolved is a failure, because something that should have run did not.

Evidence and calculator versions come out of the subgraph state, where the nodes recorded them as
they read rows and ran calculators. Nothing is reconstructed afterwards.
"""

from app.graphs.skills.contracts import SkillContext, SkillRequest, SkillResult
from app.graphs.skills.goal_planning.definition import DEFINITION
from app.graphs.skills.goal_planning.graph import goal_planning_graph


class GoalPlanningSkill:

    """Projects a savings goal by running a fixed four step subgraph over verified records."""

    name = DEFINITION.name
    version = DEFINITION.version

    async def execute(
        self,
        request: SkillRequest,
        context: SkillContext,
        ) -> SkillResult:

        """Run the projection subgraph and translate its state into the contract the orchestrator expects."""

        state = await goal_planning_graph.ainvoke(
            {"user_id": context.user_id, "message": request.message}
        )

        if state.get("failure_reason"):
            return SkillResult(
                status="refused",
                message=state.get("answer") or "I could not project that goal.",
                evidence_ids=state.get("evidence_ids", []),
            )

        if state.get("projection") is None:
            return SkillResult(
                status="failed",
                message="I could not complete that projection.",
                evidence_ids=state.get("evidence_ids", []),
            )

        return SkillResult(
            status="answered",
            message=state["answer"],
            blocks=state.get("blocks", []),
            evidence_ids=state.get("evidence_ids", []),
            calculator_versions=state.get("calculator_versions", []),
            assumptions=state.get("assumptions", {}),
        )
