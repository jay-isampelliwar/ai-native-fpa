"""The nodes of the planner graph: the model call that answers, and the compaction that follows it."""

from datetime import date

from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from app.agent.context import PlannerContext
from app.agent.prompt import SYSTEM_BASE_INSTRUCTIONS, TOOL_USAGE_INSTRUCTIONS
from app.agent.state import PlannerState
from app.agent.tools import ALL_TOOLS
from app.services.llm import llm_service


SYSTEM_PROMPT = f"{SYSTEM_BASE_INSTRUCTIONS}\n{TOOL_USAGE_INSTRUCTIONS}"


def describe_user(profile: dict[str, str]) -> str:

    """Write the user's saved basic details as a short block for the system prompt."""

    if not profile:
        return "About the user: no basic details saved yet."

    details = "\n".join(f"- {name}: {value}" for name, value in profile.items())

    return f"About the user (from your memory):\n{details}"


async def run_agent(state: PlannerState, runtime: Runtime[PlannerContext]) -> dict:

    """Stream one model answer or tool request for the conversation so far and add it to the messages."""

    system = (
        f"{SYSTEM_PROMPT}\n{describe_user(runtime.context.profile)}\n"
        f"Today's date is {date.today().isoformat()}."
        )

    messages = [SystemMessage(system), *state["messages"]]
    answer = None

    async for chunk in llm_service.with_tools(ALL_TOOLS).astream(messages):

        answer = chunk if answer is None else answer + chunk

    if answer is None:
        return {"messages": []}

    return {"messages": [answer]}
