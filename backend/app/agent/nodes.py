"""The nodes of the planner graph: the model call that answers, and the compaction that follows it."""

from app.agent.context.compaction import compact_context
from app.agent.context.query import build_agent_query
from app.agent.state import PlannerState
from app.agent.tools.tools import TOOLS


async def run_agent(state: PlannerState) -> dict:

    """Call the model on the conversation so far, streaming its words, and return the one message it wrote."""

    from app.services.llm_service import get_explanation_model

    model = get_explanation_model().bind_tools(TOOLS)

    answer = None

    async for chunk in model.astream(build_agent_query(state)):

        answer = chunk if answer is None else answer + chunk

    if answer is None:
        return {"messages": []}

    return {"messages": [answer]}


async def run_compaction(state: PlannerState) -> dict:

    """Shrink the thread after the answer is written, returning nothing when everything already fits."""

    return await compact_context(state)
