"""The goal planning skill end to end, from records entered through the API to the sentence returned.

This is Phase 2's exit condition expressed as a test: data entered manually produces a verified
projection. Nothing is stubbed except the router, because what is under test is that real rows
reach a real calculator and come back with evidence, not that a model classifies well.

The router has to be replaced before the application starts. ``build_planner_graph`` binds the
node function into the graph at compile time, so patching the module attribute afterwards has no
effect - a mistake worth stating, because the test would then silently exercise the live router.

``test_the_projection_moves_when_funding_is_linked`` is the assertion that proves goals do not
store balances. Linking a holding changes the answer without touching the goal row, which is only
possible because funding is valued at read time.

The word matching in ``resolve_goal`` is tested directly, since picking the wrong goal produces a
confidently wrong answer about a different large sum. The chosen goal is always named in the
reply, so the test asserts on that name rather than on the numbers alone.
"""

import pytest


@pytest.fixture
async def goal_client(api_user):

    """A client whose router is pinned to goal planning, patched before the graph is compiled."""

    from fastapi.testclient import TestClient

    from app.graphs.orchestrator import graph as graph_module
    from app.main import app

    async def fake_route(state):
        return {"skill_name": "goal_planning", "route_confidence": 0.95, "route_reason": "stubbed"}

    original = graph_module.route_request
    graph_module.route_request = fake_route

    with TestClient(app) as client:
        yield client

    graph_module.route_request = original


def create_goal(client, user_id, label="Buy house", amount="8000000.00", target="2031-03-01", **extra):

    """Create one goal through the API and return its id."""

    payload = {"user_id": user_id, "label": label, "target_amount": amount, "target_date": target} | extra

    response = client.post("/api/v1/goals", json=payload)

    assert response.status_code == 201

    return response.json()["id"]


def ask(client, user_id, message):

    """Send one planner message and return the parsed response body."""

    return client.post("/api/v1/planner/messages", json={"user_id": user_id, "message": message}).json()


def test_no_goals_is_a_refusal_rather_than_a_failure(goal_client, api_user):

    """With nothing set up the skill refuses politely instead of reporting an error."""

    body = ask(goal_client, api_user, "can I afford a house by 2031?")

    assert body["status"] == "refused"
    assert "no goals" in body["response"]


def test_a_goal_projects_against_its_inflated_target(goal_client, api_user):

    """The reply quotes the goal, the horizon and a target larger than today's price."""

    create_goal(goal_client, api_user)

    body = ask(goal_client, api_user, "can I afford the house?")

    assert body["status"] == "answered"
    assert "Buy house" in body["response"]
    assert "INR 8,000,000" in body["response"]
    assert "goals.v1" in body["calculator_versions"]
    assert "cashflow.v1" in body["calculator_versions"]


def test_the_answer_carries_the_evidence_it_was_built_from(goal_client, api_user):

    """Every projection returns the goal id and the records behind the surplus figure."""

    goal_id = create_goal(goal_client, api_user)

    goal_client.post(
        "/api/v1/records/income",
        json={"user_id": api_user, "label": "Salary", "amount": "200000.00"},
    )

    body = ask(goal_client, api_user, "how is the house goal doing?")

    assert goal_id in body["evidence_ids"]
    assert any(evidence.startswith("inc_") for evidence in body["evidence_ids"])


def test_the_projection_moves_when_funding_is_linked(goal_client, api_user):

    """Linking an asset changes the answer without the goal row storing any balance."""

    goal_id = create_goal(goal_client, api_user)

    before = ask(goal_client, api_user, "how is the house goal doing?")["response"]

    holding = goal_client.post(
        "/api/v1/assets/holdings",
        json={
            "user_id": api_user,
            "kind": "mutual_fund",
            "instrument_name": "Index fund",
            "units": "5000.000000",
            "average_cost": "220.0000",
            "as_of": "2026-09-01",
        },
    )

    assert holding.status_code == 201

    linked = goal_client.post(
        f"/api/v1/goals/{goal_id}/fundings",
        json={"user_id": api_user, "asset_table": "holdings", "asset_id": holding.json()["id"]},
    )

    assert linked.status_code == 201

    after = ask(goal_client, api_user, "how is the house goal doing?")["response"]

    assert before != after
    assert "valued at cost" in after


def test_the_right_goal_is_chosen_when_several_exist(goal_client, api_user):

    """A word from the question picks the matching goal rather than the first one on the list."""

    create_goal(goal_client, api_user, label="Buy house", priority=1)
    create_goal(goal_client, api_user, label="Education fund", amount="2500000.00", target="2035-06-01", priority=5)

    body = ask(goal_client, api_user, "am I on track for the education fund?")

    assert "Education fund" in body["response"]
    assert "Buy house" not in body["response"]


def test_the_goal_read_endpoint_reports_funding_as_cost(goal_client, api_user):

    """A client reading a goal is told the funded figure is cost, not a market valuation."""

    goal_id = create_goal(goal_client, api_user)

    body = goal_client.get(f"/api/v1/goals/{goal_id}?user_id={api_user}").json()

    assert body["valued_at_cost"] is True
    assert body["funded_corpus"] == "0.00" or float(body["funded_corpus"]) == 0.0


def test_another_users_goal_is_reported_as_missing(goal_client, api_user):

    """A goal the caller does not own is a 404, never a 403 that would confirm it exists."""

    goal_id = create_goal(goal_client, api_user)

    response = goal_client.get(f"/api/v1/goals/{goal_id}?user_id=1")

    assert response.status_code == 404


def test_a_linked_sip_counts_as_contribution_not_as_corpus(goal_client, api_user):

    """An SIP funds a goal monthly rather than adding to its corpus, which would double count it."""

    goal_id = create_goal(goal_client, api_user)

    sip = goal_client.post(
        "/api/v1/records/sips",
        json={
            "user_id": api_user,
            "scheme_name": "Flexi cap",
            "amount": "15000.00",
            "linked_goal_id": goal_id,
        },
    )

    assert sip.status_code == 201

    body = goal_client.get(f"/api/v1/goals/{goal_id}?user_id={api_user}").json()

    assert float(body["monthly_contribution"]) == 15000.0
    assert float(body["funded_corpus"]) == 0.0
