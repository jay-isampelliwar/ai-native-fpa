"""The agent and tool nodes, the loop between them, and the compaction that closes the turn."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.context import PlannerContext
from app.agent.nodes import run_agent
from app.agent.state import PlannerState
from app.agent.tools import ALL_TOOLS


AGENT_NODE = "agent"
TOOLS_NODE = "tools"


def build_planner_graph(checkpointer: BaseCheckpointSaver):

    """Wire the agent, its tool loop and the compaction node, and compile against the given checkpointer."""

    builder = StateGraph(PlannerState, context_schema=PlannerContext)

    builder.add_node(AGENT_NODE, run_agent)
    builder.add_node(TOOLS_NODE, ToolNode(ALL_TOOLS))

    builder.add_edge(START, AGENT_NODE)
    builder.add_conditional_edges(AGENT_NODE, tools_condition)
    builder.add_edge(TOOLS_NODE, AGENT_NODE)

    return builder.compile(checkpointer=checkpointer)
