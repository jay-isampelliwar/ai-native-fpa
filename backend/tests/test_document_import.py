"""The upload to commit pipeline, checked for the rule that makes document import safe.

That rule is one sentence: nothing extracted reaches a record table until a person accepts it.
Several tests here exist only to hold that line - an import that is extracted but not committed
must leave the transaction tables exactly as they were, and a commit must write only the rows that
were accepted.

Extraction runs in the background, so the tests await the job rather than sleeping. A polling loop
with a timeout would pass on a fast machine and flake on a slow one, and the runner already knows
when the work is done.

``test_a_credit_line_is_not_imported_as_spending`` guards the mistake that quietly ruins every
category total: a salary credit read as a negative expense. It is worth more than the rest of the
parsing assertions combined.

Duplicate detection is tested at both levels - the same file twice, and the same transaction
arriving in two overlapping statements - because they are different mechanisms and only one of them
is obvious.

Rejected rows are asserted to survive the commit. What was extracted and refused is the evidence
for why a total does not match the statement, and deleting it makes that unanswerable.
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

AUGUST_CSV = b"""Txn Date,Narration,Withdrawal Amt.,Deposit Amt.
03/08/2026,UPI/SWIGGY/Order,845.00,
05/08/2026,SALARY CREDIT AUG,,150000.00
11/08/2026,AMAZON RETAIL,2399.50,
19/08/2026,NETFLIX SUBSCRIPTION,1499.00,
"""

MALFORMED_CSV = b"""Reference,Notes
abc,def
"""


@pytest.fixture
async def doc_client(api_user):

    """A client against the real application, with no router stub since no graph run is involved."""

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client


async def upload(client, user_id, content, filename="august.csv"):

    """Upload one document and wait for its background extraction to finish."""

    from app.services.jobs import job_runner

    response = client.post(
        "/api/v1/documents",
        data={"user_id": str(user_id)},
        files={"file": (filename, content, "text/csv")},
    )

    body = response.json()

    await job_runner.wait(body["id"])

    return response, body


async def count_transactions(user_id: int) -> int:

    """Count this user's committed transactions, which is what must not change before a commit."""

    from app.db.session import session_scope
    from app.models.orm.cashflow import ExpenseTransactionRow

    async with session_scope() as session:
        return await session.scalar(
            select(func.count()).select_from(ExpenseTransactionRow).where(
                ExpenseTransactionRow.user_id == user_id
            )
        )


async def test_an_upload_is_accepted_and_extracted_in_the_background(doc_client, api_user):

    """The upload returns 202 immediately and the import reaches extracted once the job finishes."""

    response, body = await upload(doc_client, api_user, AUGUST_CSV)

    assert response.status_code == 202
    assert body["id"].startswith("imp_")

    read = doc_client.get(f"/api/v1/documents/{body['id']}?user_id={api_user}").json()

    assert read["status"] == "extracted"
    assert read["detected_format"] == "bank_csv"
    assert read["extractor"] == "bank_csv.v1"


async def test_a_credit_line_is_not_imported_as_spending(doc_client, api_user):

    """A salary credit is skipped rather than staged as a negative expense that distorts every total."""

    _, body = await upload(doc_client, api_user, AUGUST_CSV)

    rows = doc_client.get(f"/api/v1/documents/{body['id']}/rows?user_id={api_user}").json()

    merchants = [row["payload"]["merchant"] for row in rows["rows"]]

    assert rows["total"] == 3
    assert not any("SALARY" in merchant for merchant in merchants)


async def test_extraction_stages_rows_without_touching_the_record_tables(doc_client, api_user):

    """An extracted import leaves the transaction table exactly as it was, which is the whole rule."""

    before = await count_transactions(api_user)

    await upload(doc_client, api_user, AUGUST_CSV)

    assert await count_transactions(api_user) == before


async def test_rows_are_returned_least_confident_first(doc_client, api_user):

    """A row extraction was unsure about sorts to the top, where a person's attention is worth spending."""

    csv_with_bad_date = AUGUST_CSV + b"notadate,MYSTERY CHARGE,500.00,\n"

    _, body = await upload(doc_client, api_user, csv_with_bad_date, filename="mixed.csv")

    rows = doc_client.get(f"/api/v1/documents/{body['id']}/rows?user_id={api_user}").json()["rows"]

    assert float(rows[0]["confidence"]) < 1.0
    assert rows[0]["issue"] is not None


async def test_only_accepted_rows_are_committed(doc_client, api_user):

    """A commit writes the rows a person accepted and none of the ones they did not."""

    before = await count_transactions(api_user)

    _, body = await upload(doc_client, api_user, AUGUST_CSV)

    import_id = body["id"]

    rows = doc_client.get(f"/api/v1/documents/{import_id}/rows?user_id={api_user}").json()["rows"]

    doc_client.post(
        f"/api/v1/documents/{import_id}/rows/{rows[0]['id']}/decision?user_id={api_user}",
        json={"status": "accepted"},
    )

    doc_client.post(
        f"/api/v1/documents/{import_id}/rows/{rows[1]['id']}/decision?user_id={api_user}",
        json={"status": "rejected"},
    )

    commit = doc_client.post(f"/api/v1/documents/{import_id}/commit?user_id={api_user}").json()

    assert commit["status"] == "committed"
    assert commit["rows_written"] == 1
    assert commit["import_batch_id"].startswith("batch_")
    assert await count_transactions(api_user) == before + 1


async def test_every_committed_row_carries_the_batch_id(doc_client, api_user):

    """Records written from one document share a batch id, so a bad import is reversible as a unit."""

    from app.db.session import session_scope

    _, body = await upload(doc_client, api_user, AUGUST_CSV)

    import_id = body["id"]

    doc_client.post(
        f"/api/v1/documents/{import_id}/decision?user_id={api_user}",
        json={"status": "accepted", "only_pending": True},
    )

    commit = doc_client.post(f"/api/v1/documents/{import_id}/commit?user_id={api_user}").json()

    async with session_scope() as session:
        tagged = await session.scalar(
            text("SELECT count(*) FROM expense_transactions WHERE import_batch_id = :b"),
            {"b": commit["import_batch_id"]},
        )

    assert tagged == commit["rows_written"] == 3


async def test_a_rejected_row_survives_the_commit(doc_client, api_user):

    """What was extracted and refused stays readable, since it explains why a total does not match."""

    _, body = await upload(doc_client, api_user, AUGUST_CSV)

    import_id = body["id"]

    rows = doc_client.get(f"/api/v1/documents/{import_id}/rows?user_id={api_user}").json()["rows"]

    doc_client.post(
        f"/api/v1/documents/{import_id}/rows/{rows[0]['id']}/decision?user_id={api_user}",
        json={"status": "rejected"},
    )

    doc_client.post(f"/api/v1/documents/{import_id}/commit?user_id={api_user}")

    after = doc_client.get(f"/api/v1/documents/{import_id}/rows?user_id={api_user}").json()

    assert after["rejected"] == 1


async def test_correcting_a_row_clears_its_issue(doc_client, api_user):

    """A person fixing an unreadable date makes the row committable and no longer doubtful."""

    csv_with_bad_date = AUGUST_CSV + b"notadate,MYSTERY CHARGE,500.00,\n"

    _, body = await upload(doc_client, api_user, csv_with_bad_date, filename="fixable.csv")

    import_id = body["id"]

    rows = doc_client.get(f"/api/v1/documents/{import_id}/rows?user_id={api_user}").json()["rows"]

    corrected = doc_client.patch(
        f"/api/v1/documents/{import_id}/rows/{rows[0]['id']}?user_id={api_user}",
        json={"occurred_on": "2026-08-30", "category": "shopping"},
    ).json()

    assert corrected["issue"] is None
    assert corrected["edited"] is True
    assert float(corrected["confidence"]) == 1.0
    assert corrected["payload"]["occurred_on"] == "2026-08-30"


async def test_the_same_file_uploaded_twice_returns_the_first_import(doc_client, api_user):

    """Re uploading a statement is recognised rather than importing every transaction a second time."""

    _, first = await upload(doc_client, api_user, AUGUST_CSV)

    _, second = await upload(doc_client, api_user, AUGUST_CSV)

    assert second["id"] == first["id"]
    assert second["duplicate_of_existing_upload"] is True


async def test_a_transaction_already_in_the_records_is_flagged_as_duplicate(doc_client, api_user):

    """An overlapping statement marks the repeated rows rather than silently doubling a month."""

    _, first = await upload(doc_client, api_user, AUGUST_CSV)

    doc_client.post(
        f"/api/v1/documents/{first['id']}/decision?user_id={api_user}",
        json={"status": "accepted", "only_pending": True},
    )

    doc_client.post(f"/api/v1/documents/{first['id']}/commit?user_id={api_user}")

    overlapping = AUGUST_CSV + b"27/08/2026,BLINKIT GROCERY,1200.00,\n"

    _, second = await upload(doc_client, api_user, overlapping, filename="september.csv")

    rows = doc_client.get(f"/api/v1/documents/{second['id']}/rows?user_id={api_user}").json()

    assert rows["duplicates"] == 3
    assert rows["pending"] == 1


async def test_an_unrecognised_format_fails_with_a_stated_reason(doc_client, api_user):

    """A document nothing can read is refused clearly rather than guessed at."""

    _, body = await upload(doc_client, api_user, MALFORMED_CSV, filename="mystery.csv")

    read = doc_client.get(f"/api/v1/documents/{body['id']}?user_id={api_user}").json()

    assert read["status"] == "failed"
    assert "not supported" in read["error"]


async def test_committing_twice_does_not_write_twice(doc_client, api_user):

    """A retried commit reports the existing batch rather than importing every row again."""

    _, body = await upload(doc_client, api_user, AUGUST_CSV)

    import_id = body["id"]

    doc_client.post(
        f"/api/v1/documents/{import_id}/decision?user_id={api_user}",
        json={"status": "accepted", "only_pending": True},
    )

    first = doc_client.post(f"/api/v1/documents/{import_id}/commit?user_id={api_user}").json()

    count_after_first = await count_transactions(api_user)

    second = doc_client.post(f"/api/v1/documents/{import_id}/commit?user_id={api_user}").json()

    assert second["status"] == "already_committed"
    assert second["import_batch_id"] == first["import_batch_id"]
    assert await count_transactions(api_user) == count_after_first


async def test_another_users_import_is_reported_as_missing(doc_client, api_user):

    """An import the caller does not own is a 404, never a 403 that would confirm it exists."""

    _, body = await upload(doc_client, api_user, AUGUST_CSV)

    response = doc_client.get(f"/api/v1/documents/{body['id']}?user_id=1")

    assert response.status_code == 404


async def test_an_empty_file_is_refused_at_the_door(doc_client, api_user):

    """A zero byte upload is rejected before anything is stored or extracted."""

    response = doc_client.post(
        "/api/v1/documents",
        data={"user_id": str(api_user)},
        files={"file": ("empty.csv", b"", "text/csv")},
    )

    assert response.status_code == 400
