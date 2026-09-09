"""The one node the graph has: send the conversation to the model and keep what it says.

There is nothing else in here. ``authenticate_context`` was removed because it had become a node that
returned the state it was given - identity is the ``user_id`` the request already carries, and a node
that copies a field is a step in a diagram rather than a step in a program. ``run_agent`` no longer
builds tools, a context object or a run log either, because none of those exist right now.

The whole message list is sent, not just the newest message. ``PlannerState`` is a ``MessagesState``,
so the checkpointer keyed by the conversation id has already loaded the earlier turns into it, and
passing only the last one would give the model amnesia between messages while the state quietly grew.

The system prompt goes in front of the list on every call rather than being stored in the thread. If
it were appended to the state once, editing the prompt would leave every existing conversation on the
old one until its checkpoint expired.

``ainvoke`` rather than ``invoke``: the node is awaited inside an async graph, and a blocking model
call there stalls the event loop that is meant to be pushing tokens to the browser. Nothing here
streams explicitly - LangGraph's ``messages`` stream mode taps this call from the outside.
"""

from langchain.messages import SystemMessage

from app.agent.prompt import SYSTEM_PROMPT
from app.agent.state import PlannerState


async def run_agent(state: PlannerState) -> dict:

    """Answer the conversation so far in prose, with the system prompt in front of every call."""

    from app.services.llm_service import get_explanation_model

    model = get_explanation_model()

    answer = await model.ainvoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]])

    return {"messages": [answer]}
