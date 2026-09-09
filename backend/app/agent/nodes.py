from typing import Dict

from app.agent.prompt import SYSTEM_PROMPT
from app.agent.state import PlannerState
from langchain.messages import SystemMessage, HumanMessage

FALLBACK = "I could not work that out just now."

NO_CALLER = "the agent was reached without a caller"


def authenticate_context(state: PlannerState) -> Dict:
    return {
        **state
    }


async def run_agent(state: PlannerState) -> Dict:

    """Answer this message with the full tool set, and report which tools ran and what they changed."""

    from app.services.llm_service import get_explanation_model

    llm = get_explanation_model()

    messages = state["messages"]

    user_message = HumanMessage(content=messages[-1]["content"])
    sytem_prompt = SystemMessage(content=SYSTEM_PROMPT)

    response = llm.invoke(inputs=[sytem_prompt, user_message])

    return {
        "messages" : [response]
    }
