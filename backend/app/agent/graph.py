"""The one graph every request passes through, four nodes in a straight line.

There are no conditional edges left. That is the visible consequence of replacing eleven skills with
one agent: the branches used to exist because a turn could be routed, refused, validated, paused for a
human, written and audited along several different paths, and every fork was a decision made in
ordinary Python about what a skill had returned. A turn is now one agent run, so the path is the same
every time and the file is short enough to read in one go.

    START -> authenticate_context -> agent -> END

What the model decides is which tools to call and what to say. What it still does not decide is what a
figure is - every derived number comes from a versioned calculator in ``app.calculations``, reached
through a tool, and the reply is checked against the numbers the tools returned before it is shown.

What this graph no longer guarantees, stated plainly because it used to be the headline property here:
a write no longer passes through a human. ``controlled_write`` had exactly one inbound edge, from
``request_approval``, which made "the model cannot change your records on its own" true by
construction. The tools write when called. What replaced the guarantee is narrower - nothing is ever
destroyed, and every change is recorded in the audit row - and ``app.agent.tools.writes`` is where the
trade is described.

The audit node is gone too, by explicit instruction. It ran on every path, so a request could not
answer a person without leaving a trail, and with the approval interrupt already removed that row was
the last record of what the agent did to somebody's records. Nothing replaces it. ``respond`` went with
it, because ``run_agent`` already settles the sentence and can set the refusal itself.

The checkpointer is still a required argument with no default. Nothing interrupts any more, so it is
no longer load bearing for a paused approval - but it is what carries the thread's state between
messages, and a default would make the choice of saver silent and environment dependent.

``planner_graph`` holds the compiled graph for the process. The application builds it during startup
inside the PostgreSQL checkpointer's context and assigns it here; the API reads it back off this
module. It cannot be an ``lru_cache`` factory, because the saver is an async context manager whose
connection must stay open for the life of the application rather than one call.

There is no fallback graph. A request that arrives before startup finished fails on the missing graph,
which is a deployment problem worth seeing rather than one to hide behind throwaway state.
"""

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
