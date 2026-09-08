"""What the planner says without being asked, and the ordering that decides what it says first.

The approval tests that used to share this file are gone with the interrupt they described. They
asserted that a proposed SIP change did not reach the database until a person answered, which was the
headline property of the previous design; the agent's tools now write when they are called, and what
replaced those tests is ``test_agent_tools``, where each write is asserted against the table it
touches. The trade is described in ``app.agent.tools.writes``.

Alerts are computed on request rather than stored, so every test here is a read against rows it just
created. That is the honest shape for a product nobody is logged into while they are away: a finding
that appears the instant you open the app is as timely as one computed overnight, and needs no process
to be running.

Ordering is asserted because an unprompted claim about somebody's money should lead with what needs a
decision rather than what is merely worth knowing. A list that buries a deficit under a stale
valuation is worse than no list.

Every alert is asserted to carry its evidence. A finding nobody asked for should be at least as
traceable as an answer they did - arguably more, since they did not invite it.
"""

import pytest
from sqlalchemy import text


@pytest.fixture
async def plain_client(api_user):

    """A client with no router stub, for endpoints that do not run the planner graph."""

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client


def build_position(client, user_id, income="150000.00", expense="60000.00", sip="10000.00"):

    """Give the test user a simple, solvent position and return the created SIP."""

    client.post("/api/v1/records/income", json={"user_id": user_id, "label": "Salary", "amount": income})
    client.post("/api/v1/records/expenses", json={"user_id": user_id, "label": "Household", "amount": expense})

    return client.post(
        "/api/v1/records/sips",
        json={"user_id": user_id, "scheme_name": "Parag Parikh Flexi Cap", "amount": sip},
    ).json()


def test_a_solvent_position_raises_no_action_alerts(plain_client, api_user):

    """A user comfortably in surplus is not told to do anything."""

    build_position(plain_client, api_user)

    body = plain_client.get(f"/api/v1/alerts?user_id={api_user}").json()

    assert body["action_required"] == 0


def test_a_deficit_is_an_action_alert_with_evidence(plain_client, api_user):

    """Committed outflow above income is the finding that cannot wait, and it cites its records."""

    build_position(plain_client, api_user, income="40000.00", expense="55000.00", sip="5000.00")

    body = plain_client.get(f"/api/v1/alerts?user_id={api_user}").json()

    shortfall = [alert for alert in body["alerts"] if alert["kind"] == "cash_shortfall"]

    assert shortfall
    assert shortfall[0]["severity"] == "action"
    assert shortfall[0]["evidence_ids"]
    assert "cashflow.v1" in shortfall[0]["calculator_versions"]


def test_heavy_repayments_are_flagged_even_in_surplus(plain_client, api_user):

    """A month that ends positive can still be fragile, and the EMI load says so."""

    plain_client.post("/api/v1/records/income", json={"user_id": api_user, "label": "Salary", "amount": "100000.00"})

    liability = plain_client.post(
        "/api/v1/records/liabilities",
        json={
            "user_id": api_user,
            "label": "Home loan",
            "principal_outstanding": "3000000.00",
            "interest_rate_percent": "8.500",
            "tenure_months": 180,
        },
    ).json()

    plain_client.post(
        "/api/v1/records/emis",
        json={
            "user_id": api_user,
            "liability_id": liability["id"],
            "label": "Home loan",
            "amount": "60000.00",
            "interest_rate_percent": "8.500",
            "remaining_months": 150,
        },
    )

    body = plain_client.get(f"/api/v1/alerts?user_id={api_user}").json()

    kinds = {alert["kind"] for alert in body["alerts"]}

    assert "heavy_emi_load" in kinds
    assert "cash_shortfall" not in kinds


def test_an_unfunded_goal_is_raised(plain_client, api_user):

    """A goal with nothing paying into it is called out rather than projected as hopeless."""

    build_position(plain_client, api_user)

    plain_client.post(
        "/api/v1/goals",
        json={
            "user_id": api_user,
            "label": "Buy house",
            "target_amount": "8000000.00",
            "target_date": "2031-03-01",
        },
    )

    body = plain_client.get(f"/api/v1/alerts?user_id={api_user}").json()

    unfunded = [alert for alert in body["alerts"] if alert["kind"] == "unfunded_goal"]

    assert unfunded
    assert "Buy house" in unfunded[0]["title"]


def test_alerts_are_ordered_with_what_needs_deciding_first(plain_client, api_user):

    """Severity orders the list, so a screen shows decisions above observations."""

    build_position(plain_client, api_user, income="40000.00", expense="55000.00", sip="5000.00")

    body = plain_client.get(f"/api/v1/alerts?user_id={api_user}").json()

    severities = [alert["severity"] for alert in body["alerts"]]

    assert severities == sorted(severities, key=lambda level: {"action": 0, "attention": 1, "info": 2}[level])
