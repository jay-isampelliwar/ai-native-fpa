"""Projecting a goal, from records entered through the API to the figures the tool hands the model.

This was the skill's test file and it is now the tool's. What changed in the code is that the model
passes a goal id rather than a name: the old skill resolved a name by word overlap and, when nothing
matched, silently projected whichever goal sorted first - so "how are my goals doing" produced a
confident answer about one of five with no sign the others existed. ``project_goal`` takes an id, and
``test_an_unknown_goal_id_is_refused_with_the_way_to_find_one`` is the replacement for that failure.

The projection itself is unchanged and so are the properties worth asserting. Nothing is stubbed
except nothing at all - real rows reach the real calculator, because the arithmetic is the part a
person will act on.

``test_the_projection_moves_when_funding_is_linked`` is the assertion that proves goals do not store
balances. Linking a holding changes the numbers without touching the goal row, which is only possible
because funding is valued at read time.

Holdings are valued at cost rather than at market, and the tool says so in a field rather than leaving
the model to guess. There is no price feed here, and a projection that implied a market valuation
would be the one fabrication this design forbids.
"""

from decimal import Decimal

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def goal_client(api_user):

    """A plain client, since these endpoints write records rather than run the planner graph."""

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client


def context_for(user_id: int):

    """Build the context the graph would hand the agent for one turn."""

    from app.agent.state import AgentContext

    return AgentContext(user_id=user_id, conversation_id="conv_goal", correlation_id="req_goal")


async def project(user_id: int, goal_id: str) -> dict:

    """Run the projection tool the way the agent would, with an id it was given by list_goals."""

    from app.agent.state import RunLog
    from app.agent.tools import build_tools

    tools = {tool.name: tool for tool in build_tools(context_for(user_id), RunLog())}

    return await tools["project_goal"].ainvoke({"goal_id": goal_id})


async def listed(user_id: int) -> dict:

    """List the goals the way the agent would before choosing one to project."""

    from app.agent.state import RunLog
    from app.agent.tools import build_tools

    tools = {tool.name: tool for tool in build_tools(context_for(user_id), RunLog())}

    return await tools["list_goals"].ainvoke({})


def create_goal(client, user_id, label="Buy house", amount="8000000.00", target="2031-03-01", **extra):

    """Create one goal through the API and return its id."""

    payload = {"user_id": user_id, "label": label, "target_amount": amount, "target_date": target} | extra

    response = client.post("/api/v1/goals", json=payload)

    assert response.status_code == 201

    return response.json()["id"]


async def test_no_goals_means_nothing_to_list(goal_client, api_user):

    """With nothing set up the listing is empty and says so, rather than reporting an error."""

    result = await listed(api_user)

    assert result["goals"] == []
    assert "no goals" in result["note"]


async def test_an_unknown_goal_id_is_refused_with_the_way_to_find_one(goal_client, api_user):

    """An invented id is refused by name and points at the tool that returns the real ones."""

    result = await project(api_user, "goal_invented")

    assert "list_goals" in result["note"]


async def test_a_goal_projects_against_its_inflated_target(goal_client, api_user):

    """The projection quotes the goal, the horizon and a target larger than today's price."""

    goal_id = create_goal(goal_client, api_user)

    result = await project(api_user, goal_id)

    assert result["goal"] == "Buy house"
    assert result["target_today"] == "8000000.00"
    assert Decimal(result["target_at_maturity"]) > Decimal(result["target_today"])
    assert result["calculator"] == "goals.v1"


async def test_the_projection_carries_the_evidence_it_was_built_from(goal_client, api_user):

    """A projection cites the goal row it read, so a figure can be traced even with no funding linked."""

    from app.agent.state import RunLog
    from app.agent.tools import build_tools

    goal_id = create_goal(goal_client, api_user)

    log = RunLog()

    tools = {tool.name: tool for tool in build_tools(context_for(api_user), log)}

    await tools["project_goal"].ainvoke({"goal_id": goal_id})

    assert goal_id in log.evidence_ids
    assert log.calculator_versions == ["goals.v1"]


async def test_the_projection_moves_when_funding_is_linked(goal_client, api_user):

    """Linking an asset changes the answer without the goal row storing any balance."""

    goal_id = create_goal(goal_client, api_user)

    before = await project(api_user, goal_id)

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

    after = await project(api_user, goal_id)

    assert Decimal(after["projected_corpus"]) > Decimal(before["projected_corpus"])
    assert after["funding_valued_at_cost"] is True


async def test_every_goal_is_listed_rather_than_one_being_chosen(goal_client, api_user):

    """Listing names all of them, which is what the old word matching resolver could never do."""

    create_goal(goal_client, api_user, label="Buy house", priority=1)
    create_goal(goal_client, api_user, label="Education fund", amount="2500000.00", target="2035-06-01", priority=5)

    result = await listed(api_user)

    assert [goal["label"] for goal in result["goals"]] == ["Buy house", "Education fund"]


async def test_the_goal_read_endpoint_reports_funding_as_cost(goal_client, api_user):

    """A client reading a goal is told the funded figure is cost, not a market valuation."""

    goal_id = create_goal(goal_client, api_user)

    body = goal_client.get(f"/api/v1/goals/{goal_id}?user_id={api_user}").json()

    assert body["valued_at_cost"] is True
    assert body["funded_corpus"] == "0.00" or float(body["funded_corpus"]) == 0.0


async def test_another_users_goal_is_reported_as_missing(goal_client, api_user):

    """A goal the caller does not own is a 404, never a 403 that would confirm it exists."""

    goal_id = create_goal(goal_client, api_user)

    response = goal_client.get(f"/api/v1/goals/{goal_id}?user_id=1")

    assert response.status_code == 404


async def test_a_linked_sip_counts_as_contribution_not_as_corpus(goal_client, api_user):

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
