"""The agent and tool nodes, the loop between them, and the compaction that closes the turn."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import run_agent
from app.agent.state import PlannerState


AGENT_NODE = "agent"


def build_planner_graph(checkpointer: BaseCheckpointSaver):

    """Wire the agent, its tool loop and the compaction node, and compile against the given checkpointer."""

    builder = StateGraph(PlannerState)

    builder.add_node(AGENT_NODE, run_agent)

    builder.add_edge(START, AGENT_NODE)
    builder.add_edge(AGENT_NODE, END)

    return builder.compile(checkpointer=checkpointer)
