"""The SIP modification subgraph: parse, assess, propose, and then stop.

Three nodes and no branches. The skill's whole job is to turn a sentence into a proposal that a
human can approve, and it deliberately has no fourth node that applies anything - the write lives
in the top level graph, behind ``request_approval``, and is reached only after a decision.

Failures fall through rather than branching. A request whose amount could not be read records a
``failure_reason``, and the nodes below it return nothing because ``target_sip`` is unset. One
path means one place where the failure has to be handled correctly.

Compiled without a checkpointer, like the goal planning subgraph. The pause that matters belongs
to the top level graph, which holds the durable state for the whole request; this subgraph runs to
completion inside one node of it.
"""

from langgraph.graph import END, START, StateGraph

from app.graphs.skills.sip_modification.nodes import assess_affordability, parse_request, propose_change
from app.graphs.skills.sip_modification.schemas import SipModificationState


def build_sip_modification_graph():

    """Wire parse, assess and propose in order and compile them into a runnable subgraph."""

    builder = StateGraph(SipModificationState)

    builder.add_node("parse_request", parse_request)
    builder.add_node("assess_affordability", assess_affordability)
    builder.add_node("propose_change", propose_change)

    builder.add_edge(START, "parse_request")
    builder.add_edge("parse_request", "assess_affordability")
    builder.add_edge("assess_affordability", "propose_change")
    builder.add_edge("propose_change", END)

    return builder.compile()


sip_modification_graph = build_sip_modification_graph()
