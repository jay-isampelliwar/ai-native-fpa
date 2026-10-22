"""The memory loader, the agent, the approval gate before tools, and the loop between agent and tools."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.approval import approval_gate
from app.agent.context import PlannerContext
from app.agent.nodes import AGENT_NODE, APPROVAL_NODE, MEMORY_NODE, TOOLS_NODE, load_memories, run_agent
from app.agent.state import PlannerState
from app.agent.tools import ALL_TOOLS
from app.agent.tools.results import finish_tool_call


def after_tools(state: PlannerState) -> str:

    """Go back to the agent for a reply, or stop when the turn was closed without one."""

    if state.get("skip_reply"):
        return END

    return AGENT_NODE


def build_planner_graph(checkpointer: BaseCheckpointSaver):

    """Wire memory loading before the agent, the approval gate between agent and tools, and compile against the given checkpointer."""

    builder = StateGraph(PlannerState, context_schema=PlannerContext)

    builder.add_node(MEMORY_NODE, load_memories)
    builder.add_node(AGENT_NODE, run_agent)
    builder.add_node(APPROVAL_NODE, approval_gate, destinations=(TOOLS_NODE, AGENT_NODE, END))
    builder.add_node(TOOLS_NODE, ToolNode(ALL_TOOLS, awrap_tool_call=finish_tool_call))

    builder.add_edge(START, MEMORY_NODE)
    builder.add_edge(MEMORY_NODE, AGENT_NODE)
    builder.add_conditional_edges(AGENT_NODE, tools_condition, {"tools": APPROVAL_NODE, END: END})
    builder.add_conditional_edges(TOOLS_NODE, after_tools, [AGENT_NODE, END])

    return builder.compile(checkpointer=checkpointer)
