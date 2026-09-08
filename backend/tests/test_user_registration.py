"""Claiming a user id, which nothing did before a person reached the one call that writes.

Identity in this phase is an integer a client sends. Every record table has a foreign key to
``users`` and the import tables have none, so an id nobody had created could upload a statement,
extract it and stage a dozen rows before anything noticed - and what noticed was a foreign key
violation at the commit, after all the review work, with the whole transaction rolled back.

The test that matters here is the third one. Registering an id is trivial and idempotent, and asserting
that in isolation would prove almost nothing; what needed proving is that a person who has just
claimed an id can carry a file all the way into their records without meeting the constraint that
used to stop them.

The sheet reader is stubbed. What is under test is whether a fresh user can complete the pipeline,
not what a model makes of a workbook, and the two failures should never be able to mask each other.
"""

import pytest

pytestmark = pytest.mark.asyncio

FRESH_USER = 9315


@pytest.fixture
async def client():

    """A client against the real application, with no user rows created for it in advance."""

    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import database_reachable, purge

    if not await database_reachable():
        pytest.skip("postgres is not reachable")

    await purge(FRESH_USER)

    with TestClient(app) as test_client:
        yield test_client

    await purge(FRESH_USER)


async def test_registering_an_id_creates_the_person(client):

    """The row every other table points at is created by the call a client makes on its first visit."""

    body = client.post("/api/v1/users", json={"user_id": FRESH_USER}).json()

    assert body["id"] == FRESH_USER
    assert body["created"] is True
    assert body["display_name"] == f"User {FRESH_USER}"


async def test_registering_twice_is_a_return_visit_rather_than_a_conflict(client):

    """A client calls this on every visit, so the second call must be as ordinary as the first."""

    client.post("/api/v1/users", json={"user_id": FRESH_USER, "display_name": "Someone"})

    again = client.post("/api/v1/users", json={"user_id": FRESH_USER, "display_name": "Ignored"}).json()

    assert again["created"] is False
    assert again["display_name"] == "Someone"


async def test_a_newly_registered_person_can_import_a_file_into_their_records(client, monkeypatch):

    """The whole point: a person who just claimed an id can upload, review and commit without a constraint stopping them."""

    from sqlalchemy import func, select

    from app.db.session import session_scope
    from app.models.orm.cashflow import IncomeRecordRow
    from app.models.orm.credit import EmiRecordRow
    from app.services.jobs import job_runner
    from tests.fixtures_workbooks import plan_workbook
    from tests.test_holdings_import import stub_reading

    client.post("/api/v1/users", json={"user_id": FRESH_USER})

    stub_reading(
        monkeypatch,
        [
            {
                "sheet": "2_Income",
                "kind": "income",
                "header_row": 1,
                "fields": [
                    {"field": "label", "column": "Source"},
                    {"field": "amount", "column": "Amount"},
                    {"field": "frequency", "column": "How often"},
                ],
            },
            {
                "sheet": "8_Loans",
                "kind": "emi",
                "header_row": 1,
                "fields": [
                    {"field": "label", "column": "Loan"},
                    {"field": "amount", "column": "EMI"},
                    {"field": "remaining_months", "column": "Months left"},
                ],
            },
        ],
    )

    upload = client.post(
        "/api/v1/documents",
        data={"user_id": str(FRESH_USER)},
        files={"file": ("plan.xlsx", plan_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()

    await job_runner.wait(upload["id"])

    client.post(
        f"/api/v1/documents/{upload['id']}/decision?user_id={FRESH_USER}",
        json={"status": "accepted", "only_pending": True},
    )

    outcome = client.post(f"/api/v1/documents/{upload['id']}/commit?user_id={FRESH_USER}").json()

    assert outcome["status"] == "committed"

    async with session_scope() as session:

        income = await session.scalar(
            select(func.count()).select_from(IncomeRecordRow).where(IncomeRecordRow.user_id == FRESH_USER)
        )

        emis = await session.scalar(
            select(func.count()).select_from(EmiRecordRow).where(EmiRecordRow.user_id == FRESH_USER)
        )

    assert income == 2
    assert emis == 1


async def test_an_unregistered_id_is_refused_at_the_upload(client):

    """The failure belongs at the door: reviewing a dozen rows and then hitting a constraint is the old bug."""

    from tests.fixtures_workbooks import plan_workbook

    response = client.post(
        "/api/v1/documents",
        data={"user_id": str(FRESH_USER)},
        files={"file": ("plan.xlsx", plan_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "no such user"
