"""The single node of the planner graph: one model call that answers the thread in prose.

The call is ``astream`` rather than ``ainvoke`` so the words leave the model one chunk at a time.
LangGraph's ``messages`` stream mode taps the model call, not the node's return value, so this is
the only place tokens can be made to exist before the node finishes. ``ainvoke`` can be tapped the
same way when a streaming callback happens to be attached, but that is a property of the caller;
streaming here does not depend on how the graph was started.

The chunks are added back together and the whole message is returned, because the checkpointer
stores what the node returns. A client that ignores every ``token`` event and reads only the closing
``done`` event still gets the complete answer.

The system prompt is prepended on every call rather than stored in the thread, so editing the prompt
changes the next reply in an existing conversation instead of only new ones.
"""

from langchain.messages import SystemMessage

from app.agent.prompt import SYSTEM_PROMPT
from app.agent.state import PlannerState


async def run_agent(state: PlannerState) -> dict:

    """Answer the conversation so far in prose, streaming the model's words as they are written."""

    from app.services.llm_service import get_explanation_model

    model = get_explanation_model()

    answer = None

    async for chunk in model.astream([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]):

        answer = chunk if answer is None else answer + chunk

    if answer is None:
        return {"messages": []}

    return {"messages": [answer]}
