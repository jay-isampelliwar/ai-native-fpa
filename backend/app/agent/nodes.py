"""The nodes of the planner graph: the model call that answers, and the compaction that follows it."""

from app.agent.state import PlannerState
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4o-mini"
)

async def run_agent(state: PlannerState) -> dict:

    messages = state["messages"]

    async for chunk in llm.astream(messages):

        answer = chunk if answer is None else answer + chunk

    if answer is None:
        return {"messages": []}

    return {"messages": [answer]}

