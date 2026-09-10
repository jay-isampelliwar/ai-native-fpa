

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.nodes import run_agent
from app.agent.state import PlannerState
from app.agent.tools.tools import TOOLS


def build_planner_graph(checkpointer: BaseCheckpointSaver):

    """Wire the agent and tool nodes into a loop and compile the graph against the given checkpointer."""

    builder = StateGraph(PlannerState)

    builder.add_node("agent", run_agent)
    builder.add_node("tools", ToolNode(TOOLS))

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "tools", END: END},
        )

    builder.add_edge("tools", "agent")

    return builder.compile(checkpointer=checkpointer)
