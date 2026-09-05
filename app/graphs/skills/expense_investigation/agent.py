"""The investigation skill: a ReAct agent, wrapped so its freedom ends at the tool set.

This is the only skill in Phase 1 that lets a model decide what happens next, and the
wrapper is what makes that safe. The agent chooses which tool to call and in what order;
it does not choose the tools, the user whose data they read, how many turns it gets, or
what happens to its answer afterwards. Those are decided here and in the definition.

``recursion_limit`` is derived from the skill's own registered budgets rather than set to
a comfortable constant. An agent loop that exhausts it is stopped mid run, and this skill
turns that into a refusal rather than an error, because a partial investigation reported
as a finding would be an answer built on incomplete data.

Evidence is collected by the tools as they return rows, not asked of the model afterwards.
By the time the agent has written its summary it has seen a dozen ids across several
calls, and any claim it makes about which ones it used is unverifiable. The collector
knows exactly which rows were read.

The result is returned with ``status="answered"`` only when the agent produced text. An
empty final message means the loop ended without a conclusion, which is a failure worth
recording rather than an empty answer worth showing.

The skill never returns a proposal. It is registered ``read_only``, and the orchestrator's
validator rejects any result from it carrying a pending approval, so the one way this
could become dangerous is closed outside this file.
"""

from langchain.agents import create_agent
from langgraph.errors import GraphRecursionError

from app.graphs.skills.contracts import SkillContext, SkillRequest, SkillResult
from app.graphs.skills.expense_investigation.definition import DEFINITION
from app.graphs.skills.expense_investigation.prompts import SYSTEM_PROMPT
from app.graphs.skills.expense_investigation.tools import EvidenceCollector, build_expense_tools
from app.repositories.expense_repository import ExpenseRepository
from app.services.llm_service import get_explanation_model


class ExpenseInvestigationSkill:

    """Explains a change in spending by letting a model choose its reads inside a fixed tool set."""

    name = DEFINITION.name
    version = DEFINITION.version

    def __init__(self, repository: ExpenseRepository | None = None) -> None:

        """Keep the repository the tools will read from, injectable so evaluations run against fixtures."""

        self._repository = repository

    async def execute(
        self,
        request: SkillRequest,
        context: SkillContext,
        ) -> SkillResult:

        """Run the agent loop within its registered budget and report what it found, with evidence."""

        evidence = EvidenceCollector()

        tools = build_expense_tools(context, evidence, repository=self._repository)

        agent = create_agent(
            model=get_explanation_model(),
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
        )

        try:
            state = await agent.ainvoke(
                {"messages": [("user", request.message)]},
                config={"recursion_limit": self.recursion_limit()},
            )

        except GraphRecursionError:
            return SkillResult(
                status="refused",
                message="I could not finish looking into that within the steps allowed for this question.",
                evidence_ids=evidence.ids,
            )

        answer = self.final_text(state)

        if not answer:
            return SkillResult(
                status="failed",
                message="I could not reach a conclusion about that spending change.",
                evidence_ids=evidence.ids,
            )

        return SkillResult(
            status="answered",
            message=answer,
            evidence_ids=evidence.ids,
        )

    def recursion_limit(self) -> int:

        """Derive the loop ceiling from the skill's registered budgets so the definition stays authoritative."""

        return DEFINITION.maximum_model_calls + DEFINITION.maximum_tool_calls

    def final_text(self, state: dict) -> str:

        """Take the agent's closing message, returning empty when the loop ended without one."""

        messages = state.get("messages", [])

        if not messages:
            return ""

        content = getattr(messages[-1], "content", "")

        return content.strip() if isinstance(content, str) else ""
