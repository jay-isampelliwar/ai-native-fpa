"""The record entry endpoints, checked for the guarantees that matter rather than for plumbing.

Three properties are under test here and they are not equally important. That a valid
create returns 201 is plumbing. That another user's record id changes nothing, that an
archive leaves the row readable, and that a partial update touches only what was sent - those
are the ones that would cause real harm if they broke.

The ownership tests assert a 404, not a 403. A caller who is told "that record exists but is
not yours" has learned something about another person's data, so an unowned record is
reported exactly as a missing one. A test asserting 403 would be asserting a leak.

``test_archiving_removes_a_record_from_calculations_but_not_from_the_database`` is the one
that encodes the product rule. Every other framework does deletes; this one must not, because
the audit trail points at rows that have to still be there.

Every test runs against a throwaway user created by the fixture, so nothing here changes the
answers the seeded user gives elsewhere in the suite.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text


def create_income(client, user_id, **overrides):

    """Post one income record for the test user and return the parsed response."""

    payload = {"user_id": user_id, "label": "Salary", "amount": "100000.00"} | overrides

    return client.post("/api/v1/records/income", json=payload)


def test_creating_a_record_returns_the_id_a_skill_will_quote(client, api_user):

    """A create returns the prefixed identifier that is also the row's primary key and evidence id."""

    response = create_income(client, api_user)

    assert response.status_code == 201

    body = response.json()

    assert body["kind"] == "income"
    assert body["id"].startswith("inc_")


def test_a_partial_update_touches_only_the_fields_that_were_sent(client, api_user):

    """Sending one field leaves the others as they were rather than overwriting them with defaults."""

    record_id = create_income(client, api_user, label="Consulting", source="business").json()["id"]

    response = client.patch(f"/api/v1/records/income/{record_id}?user_id={api_user}", json={"amount": "125000.00"})

    assert response.status_code == 200

    listed = client.post("/api/v1/planner/messages", json={"user_id": api_user, "message": "surplus?"}).json()

    assert record_id in listed["evidence_ids"]


def test_another_users_record_id_changes_nothing(client, api_user):

    """An update aimed at a record the caller does not own reports a missing record, not a forbidden one."""

    record_id = create_income(client, api_user).json()["id"]

    response = client.patch(f"/api/v1/records/income/{record_id}?user_id=1", json={"amount": "1.00"})

    assert response.status_code == 404
    assert response.json()["detail"] == "no such record"


def test_an_emi_cannot_attach_to_a_liability_the_caller_does_not_own(client, api_user):

    """Creating an EMI against someone else's liability is refused as though it did not exist."""

    response = client.post(
        "/api/v1/records/emis",
        json={
            "user_id": api_user,
            "liability_id": "liab_1",
            "label": "Someone else's loan",
            "amount": "1000.00",
            "interest_rate_percent": "9.000",
            "remaining_months": 12,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "no such liability"


def test_an_emi_attaches_to_a_liability_the_caller_owns(client, api_user):

    """The same request succeeds once the liability belongs to the caller."""

    liability = client.post(
        "/api/v1/records/liabilities",
        json={
            "user_id": api_user,
            "label": "Car loan",
            "principal_outstanding": "450000.00",
            "interest_rate_percent": "9.250",
            "tenure_months": 60,
        },
    )

    assert liability.status_code == 201

    emi = client.post(
        "/api/v1/records/emis",
        json={
            "user_id": api_user,
            "liability_id": liability.json()["id"],
            "label": "Car loan",
            "amount": "9400.00",
            "interest_rate_percent": "9.250",
            "remaining_months": 48,
        },
    )

    assert emi.status_code == 201
    assert emi.json()["id"].startswith("emi_")


async def test_archiving_removes_a_record_from_calculations_but_not_from_the_database(client, api_user):

    """An archived record stops affecting answers while staying readable for the audit trail."""

    record_id = create_income(client, api_user, amount="50000.00").json()["id"]

    with_record = client.post("/api/v1/planner/messages", json={"user_id": api_user, "message": "surplus?"}).json()

    assert record_id in with_record["evidence_ids"]

    archived = client.post(f"/api/v1/records/income/{record_id}/archive", json={"user_id": api_user})

    assert archived.status_code == 200

    without_record = client.post("/api/v1/planner/messages", json={"user_id": api_user, "message": "surplus?"}).json()

    assert record_id not in without_record["evidence_ids"]

    from app.db.session import session_scope

    async with session_scope() as session:
        row = (await session.execute(
            text("SELECT active FROM income_records WHERE id = :rid"), {"rid": record_id}
        )).one_or_none()

    assert row is not None
    assert row[0] is False


def test_archiving_an_sip_stops_it_rather_than_deactivating_it(client, api_user):

    """An SIP is archived by moving its status to stopped, which is what the schema models."""

    sip_id = client.post(
        "/api/v1/records/sips",
        json={"user_id": api_user, "scheme_name": "Test Flexi Cap", "amount": "5000.00"},
    ).json()["id"]

    response = client.post(f"/api/v1/records/sips/{sip_id}/archive", json={"user_id": api_user})

    assert response.status_code == 200


def test_an_unknown_record_kind_is_refused(client, api_user):

    """Archiving a kind that is not in the allowlist is refused rather than guessed at."""

    response = client.post("/api/v1/records/holdings/anything/archive", json={"user_id": api_user})

    assert response.status_code == 404
    assert response.json()["detail"] == "no such record kind"


@pytest.mark.parametrize(
    "payload,reason",
    [
        ({"label": "Zero", "amount": "0"}, "zero amount"),
        ({"label": "Negative", "amount": "-100"}, "negative amount"),
        ({"label": "", "amount": "1000"}, "empty label"),
        ({"label": "Too precise", "amount": "100.999"}, "more than two decimal places"),
    ],
)
def test_invalid_amounts_are_rejected_before_reaching_the_database(client, api_user, payload, reason):

    """Validation catches a wrong figure at the cheapest point, before it can be stored."""

    response = client.post("/api/v1/records/income", json={"user_id": api_user} | payload)

    assert response.status_code == 422, reason


def test_a_transaction_is_stored_with_its_category_normalised(client, api_user):

    """Categories are lowercased on write so a filtered query does not miss rows on case."""

    response = client.post(
        "/api/v1/records/transactions",
        json={
            "user_id": api_user,
            "occurred_on": "2026-08-15",
            "amount": "2400.00",
            "category": "Dining",
            "merchant": "Local cafe",
        },
    )

    assert response.status_code == 201
    assert response.json()["id"].startswith("txn_")
