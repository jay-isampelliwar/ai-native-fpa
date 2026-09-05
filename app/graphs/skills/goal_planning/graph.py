"""The goal planning subgraph: four nodes in a straight line, compiled once per process.

There is no conditional edge here and that is the point. Every goal question follows the same
path, so the graph is a sequence rather than a decision tree, and reading it tells you exactly
what will happen to any question this skill receives.

Failures do not branch either. ``resolve_goal`` recording a ``failure_reason`` does not skip
the nodes below it; they check for a missing snapshot and return nothing, and ``compose_answer``
reports the reason. Branching around them would mean two paths to the answer and two places to
keep the failure handling correct.

This subgraph compiles without a checkpointer. It never interrupts - nothing here needs a
human, since nothing here writes - so there is no paused state to persist. The top level graph
holds the durable state for the request that called it.

Compiling once at import is safe because the graph is stateless. Every invocation supplies its
own state, and the nodes hold no data between runs.
"""

from langgraph.graph import END, START, StateGraph

from app.graphs.skills.goal_planning.nodes import compose_answer, load_cashflow, project_goal, resolve_goal
from app.graphs.skills.goal_planning.schemas import GoalPlanningState


def build_goal_planning_graph():

    """Wire the four projection steps in order and compile them into a runnable subgraph."""

    builder = StateGraph(GoalPlanningState)

    builder.add_node("resolve_goal", resolve_goal)
    builder.add_node("load_cashflow", load_cashflow)
    builder.add_node("project_goal", project_goal)
    builder.add_node("compose_answer", compose_answer)

    builder.add_edge(START, "resolve_goal")
    builder.add_edge("resolve_goal", "load_cashflow")
    builder.add_edge("load_cashflow", "project_goal")
    builder.add_edge("project_goal", "compose_answer")
    builder.add_edge("compose_answer", END)

    return builder.compile()


goal_planning_graph = build_goal_planning_graph()
