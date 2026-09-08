"""The one graph every request passes through, four nodes in a straight line.

There are no conditional edges left. That is the visible consequence of replacing eleven skills with
one agent: the branches used to exist because a turn could be routed, refused, validated, paused for a
human, written and audited along several different paths, and every fork was a decision made in
ordinary Python about what a skill had returned. A turn is now one agent run, so the path is the same
every time and the file is short enough to read in one go.

    START -> authenticate_context -> run_agent -> write_audit_record -> respond -> END

What the model decides is which tools to call and what to say. What it still does not decide is what a
figure is - every derived number comes from a versioned calculator in ``app.calculations``, reached
through a tool, and the reply is checked against the numbers the tools returned before it is shown.

What this graph no longer guarantees, stated plainly because it used to be the headline property here:
a write no longer passes through a human. ``controlled_write`` had exactly one inbound edge, from
``request_approval``, which made "the model cannot change your records on its own" true by
construction. The tools write when called. What replaced the guarantee is narrower - nothing is ever
destroyed, and every change is recorded in the audit row - and ``app.agent.tools.writes`` is where the
trade is described.

``write_audit_record`` still sits in front of ``respond`` on every path, so a request cannot answer a
person without leaving a trail.

The checkpointer is still a required argument with no default. Nothing interrupts any more, so it is
no longer load bearing for a paused approval - but it is what carries the thread's state between
messages, and a default would make the choice of saver silent and environment dependent.

``set_planner_graph`` and ``get_planner_graph`` hold the compiled graph for the process. The
application builds it during startup inside the PostgreSQL checkpointer's context and registers it
here; the API reads it back. It cannot be an ``lru_cache`` factory, because the saver is an async
context manager whose connection must stay open for the life of the application rather than one call.

``get_planner_graph`` raises rather than building a fallback. A request that arrives before startup
finished is a deployment problem, and answering it from a graph with throwaway state would hide that.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import authenticate_context, respond, run_agent, write_audit_record
from app.agent.state import PlannerState


def build_planner_graph(checkpointer: BaseCheckpointSaver):

    """Wire every node and edge of the top level graph and compile it against the given checkpointer."""

    builder = StateGraph(PlannerState)

    builder.add_node("authenticate_context", authenticate_context)
    builder.add_node("agent", run_agent)
    builder.add_node("write_audit_record", write_audit_record)
    builder.add_node("respond", respond)

    builder.add_edge(START, "authenticate_context")
    builder.add_edge("authenticate_context", "agent")
    builder.add_edge("agent", "write_audit_record")
    builder.add_edge("write_audit_record", "respond")
    builder.add_edge("respond", END)

    return builder.compile(checkpointer=checkpointer)


_planner_graph = None


def set_planner_graph(graph) -> None:

    """Register the graph compiled during startup as the one this process serves requests with."""

    global _planner_graph

    _planner_graph = graph


def get_planner_graph():

    """Return the graph registered at startup, refusing to invent one if startup has not run."""

    if _planner_graph is None:
        raise RuntimeError("the planner graph has not been built, application startup did not complete")

    return _planner_graph
