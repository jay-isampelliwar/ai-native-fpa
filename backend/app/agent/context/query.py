"""Assembling one model call: the four context blocks in a fixed order, then the thread itself."""

from langchain_core.messages import BaseMessage, SystemMessage

from app.agent.context.messages import recent_messages
from app.agent.context.profile import render_profile
from app.agent.context.structured_state import render_structured_state
from app.agent.context.summary import render_summary
from app.agent.prompt import STSTEM_BASEE_INSTUCTIONS, SYSTEM_PROMPT, TOOL_RESTRICTIONS
from app.agent.state import PlannerState


def instructions() -> str:

    """Pick the standing instructions, falling back while the newer prompt is still an empty string."""

    return STSTEM_BASEE_INSTUCTIONS or SYSTEM_PROMPT


def context_blocks(state: PlannerState) -> list[str]:

    """Render the four budgeted blocks in the order the model should read them."""

    return [
        render_profile(state),
        render_summary(state),
        render_structured_state(state),
    ]


def build_agent_query(state: PlannerState) -> list[BaseMessage]:

    """Build the messages one model call is given: instructions, restrictions, context, then the thread."""

    framing = [instructions(), TOOL_RESTRICTIONS, *context_blocks(state)]

    return [SystemMessage(content=block) for block in framing] + recent_messages(state)
