"""The agent and tool nodes, the loop between them, and the compaction that closes the turn."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.nodes import run_agent, run_compaction
from app.agent.state import PlannerState
from app.agent.tools.tools import TOOLS

AGENT_NODE = "agent"
TOOLS_NODE = "tools"
COMPACT_NODE = "compact"


def build_planner_graph(checkpointer: BaseCheckpointSaver):

    """Wire the agent, its tool loop and the compaction node, and compile against the given checkpointer."""

    builder = StateGraph(PlannerState)

    builder.add_node(AGENT_NODE, run_agent)
    builder.add_node(TOOLS_NODE, ToolNode(TOOLS))
    builder.add_node(COMPACT_NODE, run_compaction)

    builder.add_edge(START, AGENT_NODE)
    builder.add_conditional_edges(
        AGENT_NODE,
        tools_condition,
        {TOOLS_NODE: TOOLS_NODE, END: COMPACT_NODE},
        )
    builder.add_edge(TOOLS_NODE, AGENT_NODE)
    builder.add_edge(COMPACT_NODE, END)

    return builder.compile(checkpointer=checkpointer)
