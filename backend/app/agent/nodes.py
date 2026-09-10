from typing import List

from langchain.messages import SystemMessage
from langchain_core.messages import BaseMessage

from app.agent.prompt import SYSTEM_PROMPT, STSTEM_BASEE_INSTUCTIONS
from app.agent.state import PlannerState
from app.agent.tools.tools import TOOLS


def get_structured_state(state: PlannerState) -> dict:

    return {
        "messages": [message.dict() for message in state["messages"]],
        "tools": [tool.dict() for tool in TOOLS],
    }

def build_agent_query(state: PlannerState) -> List[BaseMessage]: 

    query = [
        SystemMessage(content=STSTEM_BASEE_INSTUCTIONS),
        SystemMessage(content=""),
    ]

    return []

async def run_agent(state: PlannerState) -> dict:

    """Call the model on the conversation so far, streaming its words, and return the one message it wrote."""

    from app.services.llm_service import get_explanation_model

    model = get_explanation_model().bind_tools(TOOLS)

    answer = None


    async for chunk in model.astream([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]):

        answer = chunk if answer is None else answer + chunk

    if answer is None:
        return {"messages": []}

    return {"messages": [answer]}
