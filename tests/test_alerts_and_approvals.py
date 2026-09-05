"""Alerts that fire without being asked, and the approval path that guards every write.

Two features that look unrelated share one property worth testing together: both make claims about
someone's money outside the normal question and answer flow, and both have to be traceable. An
alert nobody asked for and an approval nobody can reconstruct fail in the same way.

The approval tests assert on the database rather than on the reply. A response saying a change was
applied is not evidence that it was, and the failure worth catching - a write happening before the
human answered - is invisible from the response body.

``test_the_record_is_untouched_while_approval_is_pending`` is the single most important test in the
suite. Every other guarantee degrades into a worse answer; this one degrades into money moving
without consent.

Alerts are asserted on severity and evidence, not on wording. The text is a product decision that
will change; that a deficit is an action rather than a note, and that it cites the records behind
it, is the contract.

Each test builds the exact position it needs on a throwaway user. Alerts are a function of a whole
financial picture, so a shared fixture would make one test's records change another's findings.
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


@pytest.fixture
async def sip_client(api_user):

    """A client whose router is pinned to SIP modification, patched before the graph is compiled."""

    from fastapi.testclient import TestClient

    from app.graphs.orchestrator import graph as graph_module
    from app.main import app

    async def fake_route(state):
        return {"skill_name": "sip_modification", "route_confidence": 0.97, "route_reason": "stubbed"}

    original = graph_module.route_request
    graph_module.route_request = fake_route

    with TestClient(app) as client:
        yield client

    graph_module.route_request = original


def build_position(client, user_id, income="150000.00", expense="60000.00", sip="10000.00"):

    """Give the test user a simple, solvent position and return the created SIP."""

    client.post("/api/v1/records/income", json={"user_id": user_id, "label": "Salary", "amount": income})
    client.post("/api/v1/records/expenses", json={"user_id": user_id, "label": "Household", "amount": expense})

    return client.post(
        "/api/v1/records/sips",
        json={"user_id": user_id, "scheme_name": "Parag Parikh Flexi Cap", "amount": sip},
    ).json()


async def sip_amount(sip_id: str):

    """Read one SIP's amount straight from the database, since the reply is not evidence."""

    from app.db.session import session_scope

    async with session_scope() as session:
        return (await session.execute(
            text("SELECT amount FROM sip_records WHERE id = :i"), {"i": sip_id}
        )).one()[0]


async def test_the_record_is_untouched_while_approval_is_pending(sip_client, api_user):

    """A proposed change does not reach the database until a human has answered."""

    sip = build_position(sip_client, api_user)

    body = sip_client.post(
        "/api/v1/planner/messages",
        json={"user_id": api_user, "message": "raise my flexi cap SIP to 15000"},
    ).json()

    assert body["status"] == "awaiting_approval"
    assert await sip_amount(sip["id"]) == 10000


async def test_approving_applies_the_exact_change_that_was_shown(sip_client, api_user):

    """The figure written is the one on the card, and the card is what the user approved."""

    sip = build_position(sip_client, api_user)

    proposal = sip_client.post(
        "/api/v1/planner/messages",
        json={"user_id": api_user, "message": "raise my flexi cap SIP to 15000"},
    ).json()

    card = [block for block in proposal["blocks"] if block["type"] == "approval_card"][0]

    assert card["changes"][0]["before"] == "INR 10,000"
    assert card["changes"][0]["after"] == "INR 15,000"

    sip_client.post(
        "/api/v1/planner/approvals",
        json={
            "user_id": api_user,
            "conversation_id": proposal["conversation_id"],
            "decision": "approve",
        },
    )

    assert await sip_amount(sip["id"]) == 15000


async def test_rejecting_leaves_the_record_alone(sip_client, api_user):

    """A rejected proposal changes nothing and says so."""

    sip = build_position(sip_client, api_user)

    proposal = sip_client.post(
        "/api/v1/planner/messages",
        json={"user_id": api_user, "message": "raise my flexi cap SIP to 15000"},
    ).json()

    outcome = sip_client.post(
        "/api/v1/planner/approvals",
        json={
            "user_id": api_user,
            "conversation_id": proposal["conversation_id"],
            "decision": "reject",
        },
    ).json()

    assert "Nothing was changed" in outcome["response"]
    assert await sip_amount(sip["id"]) == 10000


async def test_an_ambiguous_amount_is_refused_rather_than_guessed(sip_client, api_user):

    """A request that could mean two amounts produces no proposal at all."""

    build_position(sip_client, api_user)

    body = sip_client.post(
        "/api/v1/planner/messages",
        json={"user_id": api_user, "message": "raise my SIP 5000"},
    ).json()

    assert body["status"] == "refused"
    assert "by that amount or to that amount" in body["response"]


async def test_the_approval_is_recorded_with_what_was_shown(sip_client, api_user):

    """The stored approval keeps the before and after a person saw, not just that they agreed."""

    from app.db.session import session_scope

    build_position(sip_client, api_user)

    proposal = sip_client.post(
        "/api/v1/planner/messages",
        json={"user_id": api_user, "message": "raise my flexi cap SIP to 15000"},
    ).json()

    sip_client.post(
        "/api/v1/planner/approvals",
        json={"user_id": api_user, "conversation_id": proposal["conversation_id"], "decision": "approve"},
    )

    async with session_scope() as session:
        row = (await session.execute(
            text(
                "SELECT status, before_state, after_state, decided_by_user_id, idempotency_key "
                "FROM pending_approvals WHERE conversation_id = :c"
            ),
            {"c": proposal["conversation_id"]},
        )).one()

    assert row[0] == "approved"
    assert row[1] == {"amount": "10000.00"}
    assert row[2] == {"amount": "15000"}
    assert row[3] == api_user
    assert row[4]


async def test_the_audit_row_records_that_a_write_happened(sip_client, api_user):

    """An approved write leaves an audit row saying so, alongside the skill and its version."""

    from app.db.session import session_scope

    build_position(sip_client, api_user)

    proposal = sip_client.post(
        "/api/v1/planner/messages",
        json={"user_id": api_user, "message": "raise my flexi cap SIP to 15000"},
    ).json()

    sip_client.post(
        "/api/v1/planner/approvals",
        json={"user_id": api_user, "conversation_id": proposal["conversation_id"], "decision": "approve"},
    )

    async with session_scope() as session:
        rows = (await session.execute(
            text(
                "SELECT skill_name, skill_version, result_status, approval_decision, write_performed "
                "FROM audit_records WHERE conversation_id = :c ORDER BY recorded_at"
            ),
            {"c": proposal["conversation_id"]},
        )).all()

    assert rows[-1] == ("sip_modification", "1.0", "proposed", "approve", True)


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
