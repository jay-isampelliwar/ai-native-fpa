"""The one graph every request passes through, wired by hand and never by a model.

This file is the security boundary of the product expressed as code. A model cannot add
an edge, remove one, or jump between nodes. It contributes exactly one string inside
``route_request``, and every gate after that is ordinary Python. Read the edges below and
you have read the complete set of paths a request can take.

The property worth checking on any change here: there is no edge into
``controlled_write`` except from ``request_approval``. Approval is therefore not a
policy a skill may follow, it is the only road to a write. Adding a shortcut for
convenience would silently remove the guarantee the whole design exists to provide.

``write_audit_record`` sits in front of ``respond`` on every path, including the refusal
paths, so a request cannot answer a user without leaving a trail. That ordering is also
why refused runs still produce a record.

The checkpointer is a required argument with no default. ``request_approval`` calls
``interrupt``, so a graph without one has nowhere to persist a pending change and it dies
with the process. A default would make that failure silent and environment dependent -
working in tests, quietly wrong in production - so callers must say which one they mean.

``set_planner_graph`` and ``get_planner_graph`` hold the compiled graph for the process.
The application builds it during startup inside the PostgreSQL checkpointer's context and
registers it here; the API reads it back. It cannot be an ``lru_cache`` factory, because
the saver is an async context manager whose connection must stay open for the life of the
application rather than for the life of one call.

``get_planner_graph`` raises rather than building a fallback. A request that arrives before
startup finished is a deployment problem, and answering it from a graph with throwaway
state would hide that.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.graphs.orchestrator.edges import after_permission_check, after_routing, route_by_risk
from app.graphs.orchestrator.nodes import (
    authenticate_context,
    check_permissions,
    controlled_write,
    execute_skill,
    load_skill_definition,
    request_approval,
    respond,
    validate_skill_result,
    write_audit_record,
)
from app.graphs.orchestrator.router import route_request
from app.graphs.skills.bootstrap import register_skills
from app.graphs.orchestrator.state import PlannerState


def build_planner_graph(checkpointer: BaseCheckpointSaver):

    """Wire every node and edge of the top level graph and compile it against the given checkpointer."""

    builder = StateGraph(PlannerState)

    builder.add_node("authenticate_context", authenticate_context)
    builder.add_node("route_request", route_request)
    builder.add_node("load_skill_definition", load_skill_definition)
    builder.add_node("check_permissions", check_permissions)
    builder.add_node("execute_skill", execute_skill)
    builder.add_node("validate_skill_result", validate_skill_result)
    builder.add_node("request_approval", request_approval)
    builder.add_node("controlled_write", controlled_write)
    builder.add_node("write_audit_record", write_audit_record)
    builder.add_node("respond", respond)

    builder.add_edge(START, "authenticate_context")
    builder.add_edge("authenticate_context", "route_request")

    builder.add_conditional_edges(
        "route_request",
        after_routing,
        ["load_skill_definition", "write_audit_record"],
    )

    builder.add_edge("load_skill_definition", "check_permissions")

    builder.add_conditional_edges(
        "check_permissions",
        after_permission_check,
        ["execute_skill", "write_audit_record"],
    )

    builder.add_edge("execute_skill", "validate_skill_result")

    builder.add_conditional_edges(
        "validate_skill_result",
        route_by_risk,
        ["request_approval", "write_audit_record"],
    )

    builder.add_edge("request_approval", "controlled_write")
    builder.add_edge("controlled_write", "write_audit_record")
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
