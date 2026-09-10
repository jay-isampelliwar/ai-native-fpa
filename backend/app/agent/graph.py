from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import run_agent
from app.agent.state import PlannerState


def build_planner_graph(checkpointer: BaseCheckpointSaver):

    """Wire the one node of the graph and compile it against the given checkpointer."""

    builder = StateGraph(PlannerState)

    builder.add_node("agent", run_agent)

    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)

    return builder.compile(checkpointer=checkpointer)
