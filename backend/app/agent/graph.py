"""The one graph every request passes through: a single node between START and END.

    START -> agent -> END

There are no conditional edges and now no straight line either, because there is only one step left
to take. The branches this file used to hold existed because a turn could be routed to a skill,
refused, validated, paused for a human decision, written and audited along several different paths.
None of those exist: a turn is one model call, so the graph is one node and the file is short enough
to read at a glance.

What the graph is still for, with one node in it, is the checkpointer. ``PlannerState`` is a
``MessagesState``, and compiling against a saver is what makes the conversation id a thread whose
earlier messages come back on the next request. Without it this would be a function call, and every
message would arrive at a model with no memory of the last one.

The checkpointer is a required argument with no default. A default would make the choice of saver
silent and environment dependent, which is how a deployment ends up remembering conversations in one
process's memory and losing them on restart.

``planner_graph`` holds the compiled graph for the process. The application builds it during startup
inside the PostgreSQL checkpointer's context and assigns it here; the API reads it back off this
module. It cannot be an ``lru_cache`` factory, because the saver is an async context manager whose
connection must stay open for the life of the application rather than one call.

There is no fallback graph. A request that arrives before startup finished fails on the missing graph,
which is a deployment problem worth seeing rather than one to hide behind throwaway state.
"""

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


planner_graph = None
