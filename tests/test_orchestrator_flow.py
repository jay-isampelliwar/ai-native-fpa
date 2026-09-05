"""End to end checks that the top level graph enforces its own rules, not just that it runs.

These tests exercise the property Phase 1 exists to prove: a request reaches a versioned
skill, comes back with evidence, and cannot reach anything it lacks permission for. The
router's model call is stubbed throughout, because what is under test is the graph's
control flow rather than the quality of a classification.

The permission test is the important one. It grants a caller only some of the scopes the
skill requires and asserts the skill never executed at all - not that it executed and
returned nothing. A test that only checked the reply would pass even if the skill had run
and read records it should not have seen.

Assertions on absent fields use ``state.get`` rather than indexing. LangGraph returns the
state as a plain dict and omits keys no node ever wrote, so a field that stayed at its
default is missing from the result rather than present and None.

The checkpointer is passed explicitly. ``build_planner_graph`` has no default because the
application must never fall back to throwaway approval state; these tests choose an in
memory saver deliberately, which is a different thing from getting one by omission.

The routing tests at the end cover ``route_by_risk`` directly, because both of its conditions guard
a different mistake and only one of them is visible from an end to end run. A refusal from a write
capable skill must not pause for approval, and a result claiming to be a proposal without an
approval row must not either.
"""

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.core.security import AuthenticatedUser
from app.graphs.orchestrator import nodes
from app.graphs.orchestrator.graph import build_planner_graph
from app.graphs.skills.bootstrap import register_skills
from app.graphs.skills.registry import SkillRegistry


@pytest.fixture(autouse=True)
def registered_skills():

    """Populate the shared registry before each test so routing has something to resolve."""

    register_skills()


@pytest.fixture
def stub_router(monkeypatch):

    """Replace the router node with a fixed choice, so no model call is made during a graph run."""

    async def fake_route(state):
        return {"skill_name": "cashflow_summary", "route_confidence": 0.95, "route_reason": "stubbed"}

    monkeypatch.setattr("app.graphs.orchestrator.graph.route_request", fake_route, raising=False)

    return fake_route


async def run_graph(stub_router, monkeypatch, user=None):

    """Compile a fresh graph with the router stubbed and run one request through it."""

    import app.graphs.orchestrator.graph as graph_module

    monkeypatch.setattr(graph_module, "route_request", stub_router)

    if user is not None:
        monkeypatch.setattr(nodes, "local_user", lambda user_id: user)

    graph = build_planner_graph(InMemorySaver())

    return await graph.ainvoke(
        {"user_id": 1, "conversation_id": "conv_1", "user_message": "how much is left this month?"},
        config={"configurable": {"thread_id": "thread_1"}},
    )


async def test_request_reaches_skill_and_returns_evidence(stub_router, monkeypatch):

    """A permitted request routes to the versioned skill and comes back with traceable evidence."""

    state = await run_graph(stub_router, monkeypatch)

    assert state["skill_name"] == "cashflow_summary"
    assert state["definition"].version == "1.0"
    assert state["permission_granted"] is True
    assert state["result"].status == "answered"
    assert state["result"].evidence_ids
    assert state["result"].calculator_versions == ["cashflow.v1"]
    assert state["validation_errors"] == []
    assert "free surplus" in state["response"]


async def test_missing_scope_stops_before_the_skill_runs(stub_router, monkeypatch):

    """A caller lacking one required scope is refused, and the skill is never executed."""

    partial = AuthenticatedUser(user_id=1, scopes=frozenset({"income:read", "expenses:read"}))

    state = await run_graph(stub_router, monkeypatch, user=partial)

    assert state["permission_granted"] is False
    assert state.get("result") is None
    assert "liabilities:read" in state["denial_reason"]
    assert state["response"].startswith("I could not do that")


async def test_unregistered_skill_name_is_refused(stub_router, monkeypatch):

    """A routed name with no registered version is refused before permissions are even checked."""

    async def route_to_nothing(state):
        return {"skill_name": "definitely_not_a_skill", "route_confidence": 0.4, "route_reason": "stubbed"}

    state = await run_graph(route_to_nothing, monkeypatch)

    assert state.get("definition") is None
    assert state["permission_granted"] is False
    assert "not registered" in state["denial_reason"] or "no enabled version" in state["denial_reason"]


def test_registry_resolves_by_name_and_version():

    """A skill registered into an isolated registry resolves by both its name and its exact version."""

    isolated = SkillRegistry()

    register_skills(into=isolated)

    definition, skill = isolated.resolve("cashflow_summary", "1.0")

    assert definition.read_only is True
    assert skill.name == "cashflow_summary"


def test_a_refusal_from_a_write_capable_skill_does_not_pause_for_approval():

    """A skill that could write but produced no proposal goes to the audit record, not to a human."""

    from app.graphs.orchestrator.edges import route_by_risk
    from app.graphs.orchestrator.state import PlannerState
    from app.graphs.skills.contracts import SkillDefinition, SkillResult

    definition = SkillDefinition(
        name="sip_modification",
        version="1.0",
        description="",
        risk_level="high",
        read_only=False,
        requires_approval=True,
    )

    state = PlannerState(
        user_id=1,
        conversation_id="conv",
        user_message="raise my SIP 5000",
        definition=definition,
        result=SkillResult(status="refused", message="ambiguous"),
    )

    assert route_by_risk(state) == "write_audit_record"


def test_a_proposal_without_a_stored_approval_does_not_pause_either():

    """A result claiming to be a proposal with nothing durable behind it is not treated as one."""

    from app.graphs.orchestrator.edges import route_by_risk
    from app.graphs.orchestrator.state import PlannerState
    from app.graphs.skills.contracts import SkillDefinition, SkillResult

    definition = SkillDefinition(
        name="sip_modification",
        version="1.0",
        description="",
        risk_level="high",
        read_only=False,
        requires_approval=True,
    )

    state = PlannerState(
        user_id=1,
        conversation_id="conv",
        user_message="raise it to 15000",
        definition=definition,
        result=SkillResult(status="proposed", message="change it", pending_approval_id=None),
    )

    assert route_by_risk(state) == "write_audit_record"


def test_a_real_proposal_does_pause_for_approval():

    """Both conditions met is the only combination that reaches a human."""

    from app.graphs.orchestrator.edges import route_by_risk
    from app.graphs.orchestrator.state import PlannerState
    from app.graphs.skills.contracts import SkillDefinition, SkillResult

    definition = SkillDefinition(
        name="sip_modification",
        version="1.0",
        description="",
        risk_level="high",
        read_only=False,
        requires_approval=True,
    )

    state = PlannerState(
        user_id=1,
        conversation_id="conv",
        user_message="raise it to 15000",
        definition=definition,
        result=SkillResult(status="proposed", message="change it", pending_approval_id="appr_1"),
    )

    assert route_by_risk(state) == "request_approval"
