from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import authenticate_context, run_agent
from app.agent.state import PlannerState


def build_planner_graph(checkpointer: BaseCheckpointSaver):

    """Wire every node and edge of the top level graph and compile it against the given checkpointer."""

    builder = StateGraph(PlannerState)

    builder.add_node("authenticate_context", authenticate_context)
    builder.add_node("agent", run_agent)

    builder.add_edge(START, "authenticate_context")
    builder.add_edge("authenticate_context", "agent")
    builder.add_edge("agent", END)

    return builder.compile(checkpointer=checkpointer)


planner_graph = None
