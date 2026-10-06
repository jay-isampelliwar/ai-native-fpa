"""The nodes of the planner graph: the model call that answers, and the compaction that follows it."""

from langchain_openai import ChatOpenAI

from app.agent.state import PlannerState
from app.core.config import get_settings


settings = get_settings()

llm = ChatOpenAI(
    model=settings.CHAT_MODEL,
    api_key=settings.OPENAI_API_KEY,
    )


async def run_agent(state: PlannerState) -> dict:

    """Stream one model answer for the conversation so far and add it to the messages."""

    messages = state["messages"]
    answer = None

    async for chunk in llm.astream(messages):

        answer = chunk if answer is None else answer + chunk

    if answer is None:
        return {"messages": []}

    return {"messages": [answer]}
