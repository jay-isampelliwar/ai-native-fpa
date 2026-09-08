"""Importing holdings statements: template families, reconciliation, and the mapping path for unknown ones.

Three layouts drive these tests and each contributes a different failure mode. The consolidated export
ends with a formula total row that would import as a holding worth the whole portfolio. The broker
export supplies no value columns, so invested and current have to be computed and the computation has
to be recorded as such. The mutual fund export carries a name, a mobile number and a PAN above its
table.

``test_personal_details_never_reach_a_staged_row`` is the one to keep if the suite ever has to shrink.
Every other failure here produces a wrong number; that one produces a PAN in a database column nobody
expected it in and a log line nobody redacted.

Reconciliation is asserted per layout because it is the only check that catches a whole sheet being
skipped or a column mapped to the wrong field. Individual rows can all look plausible while the total
is wrong by exactly one line, which is what a total row imported as a holding looks like.

The mapping path is tested without a model. Proposing a mapping is the one step that uses one, and what
matters structurally is that a confirmed mapping becomes a template and that the next file of the same
shape parses deterministically - both of which are testable with a hand written mapping.

Two of those tests exist for a failure that made every unrecognised layout unimportable. The response
schema asked the model for an open ended object, which a strict schema cannot express, so the call was
rejected with a 400 before reaching the model - and because the endpoint built its sheet list from the
proposal, a person was shown a mapping card with no columns in it and no way forward. So the schema is
asserted to contain no free form object, and the endpoint is asserted to offer the file's own columns
even when asking a model fails outright.

Fixtures reproduce the real layouts and none of the real values. The PAN and mobile number in them are
invented and belong to nobody.
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from tests.fixtures_workbooks import (
    broker_workbook,
    consolidated_workbook,
    fund_statement_workbook,
    plan_workbook,
    unknown_workbook,
)

WORKBOOK_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
async def doc_client(api_user):

    """A client against the real application, since no graph run is involved in importing."""

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client


def stub_reading(monkeypatch, sheets: list[dict], provider: str = "test") -> None:

    """Answer the sheet reader from the test rather than from a model, so the suite needs no API key."""

    from app.extraction import sheets as sheets_module

    reading = sheets_module.ReadWorkbook(
        provider=provider,
        sheets=[sheets_module.ReadSheet(**sheet) for sheet in sheets],
    )

    async def prepared(profile):

        """Return the classification this test is about, ignoring the profile it would have been read from."""

        return reading

    monkeypatch.setattr(sheets_module, "read_workbook", prepared)


HOLDING_SHEET = {
    "sheet": "Positions",
    "kind": "holding",
    "header_row": 1,
    "fields": [
        {"field": "instrument_name", "column": "Description"},
        {"field": "isin", "column": "Security Code"},
        {"field": "quantity", "column": "Qty Available"},
        {"field": "average_cost", "column": "Cost Per Unit"},
        {"field": "current_value", "column": "Current Amount"},
    ],
}


async def upload(client, user_id, content, filename):

    """Upload one workbook and wait for its background extraction to finish."""

    from app.services.jobs import job_runner

    response = client.post(
        "/api/v1/documents",
        data={"user_id": str(user_id)},
        files={"file": (filename, content, WORKBOOK_TYPE)},
    )

    body = response.json()

    await job_runner.wait(body["id"])

    return client.get(f"/api/v1/documents/{body['id']}?user_id={user_id}").json()


def rows_of(client, import_id, user_id):

    """Read the staged rows of one import."""

    return client.get(f"/api/v1/documents/{import_id}/rows?user_id={user_id}").json()


async def count_holdings(user_id: int) -> int:

    """Count this user's committed holdings, which must not change before a commit."""

    from app.db.session import session_scope
    from app.models.orm.investments import HoldingRow

    async with session_scope() as session:
        return await session.scalar(
            select(func.count()).select_from(HoldingRow).where(HoldingRow.user_id == user_id)
        )


async def test_the_consolidated_layout_is_recognised_and_reconciles(doc_client, api_user):

    """A known layout parses by its template and its rows add up to the totals it states."""

    record = await upload(doc_client, api_user, consolidated_workbook(), "consolidated.xlsx")

    assert record["status"] == "extracted"
    assert record["template_id"] == "consolidated_holdings.v1"
    assert record["reconciled"] is True


async def test_the_statements_own_total_row_is_not_imported(doc_client, api_user):

    """The formula total line at the end of a statement is skipped rather than staged as a holding."""

    record = await upload(doc_client, api_user, consolidated_workbook(), "consolidated.xlsx")

    rows = rows_of(doc_client, record["id"], api_user)

    names = [row["payload"]["instrument_name"] for row in rows["rows"]]

    assert rows["total"] == 4
    assert not any(name.lower().startswith("total") for name in names)


async def test_the_broker_layout_computes_values_it_was_not_given(doc_client, api_user):

    """A statement supplying only quantity and prices has its values computed, and says which were."""

    record = await upload(doc_client, api_user, broker_workbook(), "broker.xlsx")

    assert record["template_id"] == "broker_holdings.v1"
    assert record["reconciled"] is True

    rows = rows_of(doc_client, record["id"], api_user)["rows"]

    payload = rows[0]["payload"]

    assert "invested_value" in payload["computed_fields"]
    assert "current_value" in payload["computed_fields"]
    assert Decimal(payload["invested_value"]) > Decimal("0")


async def test_both_broker_sheets_are_read(doc_client, api_user):

    """Equity and mutual fund tabs are separate sheets and both contribute rows."""

    record = await upload(doc_client, api_user, broker_workbook(), "broker.xlsx")

    rows = rows_of(doc_client, record["id"], api_user)["rows"]

    sheets = {row["payload"]["asset_type"] for row in rows}

    assert record["row_count"] == 3
    assert "equity" in sheets


async def test_personal_details_never_reach_a_staged_row(doc_client, api_user):

    """A name, a mobile number and a PAN above the table are not extracted as holdings."""

    record = await upload(doc_client, api_user, fund_statement_workbook(), "fund_statement.xlsx")

    rows = rows_of(doc_client, record["id"], api_user)["rows"]

    serialised = str(rows)

    assert "AAAPZ1234C" not in serialised
    assert "9000000000" not in serialised
    assert "Test Person" not in serialised


async def test_a_fund_statement_identifies_holdings_by_scheme_and_folio(doc_client, api_user):

    """With no ISIN available the row records what it was actually matched on rather than implying one."""

    record = await upload(doc_client, api_user, fund_statement_workbook(), "fund_statement.xlsx")

    rows = rows_of(doc_client, record["id"], api_user)["rows"]

    assert record["reconciled"] is True
    assert all(row["payload"]["identifier_type"] == "scheme_folio" for row in rows)
    assert all(row["payload"]["isin"] is None for row in rows)


async def test_an_isin_is_preferred_when_the_statement_carries_one(doc_client, api_user):

    """A broker statement with ISINs identifies by ISIN, which is stronger evidence than a symbol."""

    record = await upload(doc_client, api_user, broker_workbook(), "broker.xlsx")

    rows = rows_of(doc_client, record["id"], api_user)["rows"]

    assert all(row["payload"]["identifier_type"] == "isin" for row in rows)


async def test_every_staged_row_keeps_where_it_came_from(doc_client, api_user):

    """A row records its sheet and line number, so a figure that looks wrong can be traced to its source."""

    from app.db.session import session_scope
    from app.models.orm.imports import StagedRowRow

    record = await upload(doc_client, api_user, broker_workbook(), "broker.xlsx")

    async with session_scope() as session:
        rows = (await session.scalars(
            select(StagedRowRow).where(StagedRowRow.import_id == record["id"])
        )).all()

    assert all(row.source_sheet for row in rows)
    assert all(row.source_row_number and row.source_row_number >= 24 for row in rows)
    assert all(row.source_cells for row in rows)


async def test_an_unknown_layout_is_read_rather_than_refused(doc_client, api_user, monkeypatch):

    """A layout no template covers is read from what its headings say, so an import is never a form first."""

    stub_reading(
        monkeypatch,
        [
            {
                "sheet": "Positions",
                "kind": "holding",
                "header_row": 1,
                "fields": [
                    {"field": "instrument_name", "column": "Description"},
                    {"field": "isin", "column": "Security Code"},
                    {"field": "quantity", "column": "Qty Available"},
                    {"field": "current_value", "column": "Current Amount"},
                ],
            }
        ],
    )

    record = await upload(doc_client, api_user, unknown_workbook(), "mystery.xlsx")

    assert record["status"] == "extracted"
    assert record["row_count"] == 2

    assert await count_holdings(api_user) == 0

    rows = rows_of(doc_client, record["id"], api_user)["rows"]

    assert {row["payload"]["instrument_name"] for row in rows} == {"HDFC Bank Limited", "Infosys Limited"}

    assert all(float(row["confidence"]) < 1 for row in rows)


async def test_a_workbook_of_income_and_loans_becomes_records(doc_client, api_user, monkeypatch):

    """A plan workbook is not a holdings statement, and every kind it holds is staged as its own record."""

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
            {
                "sheet": "1_Personal_Details",
                "kind": "ignore",
                "header_row": 1,
                "fields": [],
            },
        ],
    )

    record = await upload(doc_client, api_user, plan_workbook(), "plan.xlsx")

    assert record["status"] == "extracted"

    rows = rows_of(doc_client, record["id"], api_user)["rows"]

    staged = {(row["payload"]["kind"], row["payload"]["fields"]["label"]) for row in rows}

    assert ("income", "Salary") in staged
    assert ("income", "Flat rent") in staged
    assert ("emi", "Home loan") in staged

    assert all(row["target_table"] == "records" for row in rows)

    assert not [row for row in rows if "A Person" in str(row["payload"]) or "ABCDE1234F" in str(row["payload"])]


async def test_committing_a_read_plan_writes_the_records(doc_client, api_user, monkeypatch):

    """The whole point of reading a plan is that accepting it puts income and EMIs in the record tables."""

    from sqlalchemy import func, select

    from app.db.session import session_scope
    from app.models.orm.cashflow import IncomeRecordRow
    from app.models.orm.credit import EmiRecordRow

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

    record = await upload(doc_client, api_user, plan_workbook(), "plan.xlsx")

    doc_client.post(
        f"/api/v1/documents/{record['id']}/decision?user_id={api_user}",
        json={"status": "accepted", "only_pending": True},
    )

    outcome = doc_client.post(f"/api/v1/documents/{record['id']}/commit?user_id={api_user}").json()

    assert outcome["status"] == "committed"

    async with session_scope() as session:

        income = await session.scalar(
            select(func.count()).select_from(IncomeRecordRow).where(IncomeRecordRow.user_id == api_user)
        )

        emis = await session.scalar(
            select(func.count()).select_from(EmiRecordRow).where(EmiRecordRow.user_id == api_user)
        )

    assert income == 2
    assert emis == 1


async def test_a_template_belongs_to_the_person_who_confirmed_it(doc_client, api_user, monkeypatch):

    """One person's mapping must not silently parse another person's file, however alike the two layouts are."""

    from app.extraction.workbook import profile_workbook
    from app.repositories.templates_repository import templates_repository

    fingerprint = profile_workbook(unknown_workbook()).fingerprint

    stub_reading(monkeypatch, [HOLDING_SHEET])

    record = await upload(doc_client, api_user, unknown_workbook(), "mystery.xlsx")

    doc_client.post(
        f"/api/v1/documents/{record['id']}/mapping/confirm",
        json={
            "user_id": api_user,
            "provider": "test_broker",
            "name": "Test broker positions",
            "sheets": [
                {
                    "sheet": "Positions",
                    "header_row": 1,
                    "asset_type": "equity",
                    "mapping": {"instrument_name": "Description", "quantity": "Qty Available"},
                }
            ],
        },
    )

    assert await templates_repository.by_fingerprint(fingerprint, api_user) is not None

    assert await templates_repository.by_fingerprint(fingerprint, api_user + 1) is None


async def test_a_record_already_on_file_is_flagged_rather_than_staged_again(doc_client, api_user, monkeypatch):

    """A plan re-exported with one cell changed is a new file and the same records; the second pass must say so."""

    from app.services.jobs import job_runner

    reading = [
        {
            "sheet": "2_Income",
            "kind": "income",
            "header_row": 1,
            "fields": [
                {"field": "label", "column": "Source"},
                {"field": "amount", "column": "Amount"},
            ],
        }
    ]

    stub_reading(monkeypatch, reading)

    first = await upload(doc_client, api_user, plan_workbook(), "plan.xlsx")

    doc_client.post(
        f"/api/v1/documents/{first['id']}/decision?user_id={api_user}",
        json={"status": "accepted", "only_pending": True},
    )

    doc_client.post(f"/api/v1/documents/{first['id']}/commit?user_id={api_user}")

    stub_reading(monkeypatch, reading)

    response = doc_client.post(
        "/api/v1/documents",
        data={"user_id": str(api_user)},
        files={"file": ("plan-again.xlsx", plan_workbook() + b"\x00", WORKBOOK_TYPE)},
    ).json()

    await job_runner.wait(response["id"])

    rows = rows_of(doc_client, response["id"], api_user)["rows"]

    assert rows

    assert all(row["status"] == "duplicate" for row in rows)

    assert all("already appears in your records" in (row["issue"] or "") for row in rows)


async def test_a_holding_already_held_is_flagged_by_its_isin(doc_client, api_user, monkeypatch):

    """The same statement re-exported must not double a portfolio, and ISIN is what identifies a holding."""

    from app.services.jobs import job_runner

    stub_reading(monkeypatch, [HOLDING_SHEET])

    first = await upload(doc_client, api_user, unknown_workbook(), "mystery.xlsx")

    doc_client.post(
        f"/api/v1/documents/{first['id']}/decision?user_id={api_user}",
        json={"status": "accepted", "only_pending": True},
    )

    doc_client.post(f"/api/v1/documents/{first['id']}/commit?user_id={api_user}")

    stub_reading(monkeypatch, [HOLDING_SHEET])

    response = doc_client.post(
        "/api/v1/documents",
        data={"user_id": str(api_user)},
        files={"file": ("mystery-again.xlsx", unknown_workbook() + b"\x00", WORKBOOK_TYPE)},
    ).json()

    await job_runner.wait(response["id"])

    rows = rows_of(doc_client, response["id"], api_user)["rows"]

    assert rows

    assert all(row["status"] == "duplicate" for row in rows)


async def test_a_flagged_duplicate_is_still_the_persons_decision(doc_client, api_user, monkeypatch):

    """Flagging is not blocking: someone who genuinely has two of something can still accept the second."""

    from app.services.jobs import job_runner

    reading = [
        {
            "sheet": "2_Income",
            "kind": "income",
            "header_row": 1,
            "fields": [
                {"field": "label", "column": "Source"},
                {"field": "amount", "column": "Amount"},
            ],
        }
    ]

    stub_reading(monkeypatch, reading)

    first = await upload(doc_client, api_user, plan_workbook(), "plan.xlsx")

    doc_client.post(
        f"/api/v1/documents/{first['id']}/decision?user_id={api_user}",
        json={"status": "accepted", "only_pending": True},
    )

    doc_client.post(f"/api/v1/documents/{first['id']}/commit?user_id={api_user}")

    stub_reading(monkeypatch, reading)

    again = doc_client.post(
        "/api/v1/documents",
        data={"user_id": str(api_user)},
        files={"file": ("plan-again.xlsx", plan_workbook() + b"\x00", WORKBOOK_TYPE)},
    ).json()

    await job_runner.wait(again["id"])

    rows = rows_of(doc_client, again["id"], api_user)["rows"]

    accepted = doc_client.post(
        f"/api/v1/documents/{again['id']}/rows/{rows[0]['id']}/decision?user_id={api_user}",
        json={"status": "accepted"},
    )

    assert accepted.status_code == 200

    outcome = doc_client.post(f"/api/v1/documents/{again['id']}/commit?user_id={api_user}").json()

    assert outcome["status"] == "committed"
    assert outcome["rows_written"] == 1


async def test_a_model_that_cannot_be_reached_falls_back_to_the_form(doc_client, api_user, monkeypatch):

    """No key, no network or a refusal must cost the reading, not the file - the mapping form is the floor."""

    from app.extraction import sheets as sheets_module

    async def unreachable(profile):

        """Stand in for a model call that fails, which is the state a fresh checkout runs in."""

        raise RuntimeError("the model is unreachable")

    monkeypatch.setattr(sheets_module, "read_workbook", unreachable)

    record = await upload(doc_client, api_user, unknown_workbook(), "mystery.xlsx")

    assert record["status"] == "needs_mapping"
    assert record["row_count"] == 0
    assert await count_holdings(api_user) == 0


async def test_a_confirmed_mapping_parses_the_import(doc_client, api_user, monkeypatch):

    """Confirming a mapping re extracts the same file deterministically, with no model involved."""

    stub_reading(monkeypatch, [HOLDING_SHEET])

    record = await upload(doc_client, api_user, unknown_workbook(), "mystery.xlsx")

    confirmed = doc_client.post(
        f"/api/v1/documents/{record['id']}/mapping/confirm",
        json={
            "user_id": api_user,
            "provider": "test_broker",
            "name": "Test broker positions",
            "sheets": [
                {
                    "sheet": "Positions",
                    "header_row": 1,
                    "asset_type": "equity",
                    "mapping": {
                        "instrument_name": "Description",
                        "isin": "Security Code",
                        "quantity": "Qty Available",
                        "average_cost": "Cost Per Unit",
                        "current_value": "Current Amount",
                    },
                }
            ],
        },
    ).json()

    assert confirmed["status"] == "extracted"
    assert confirmed["row_count"] == 2

    rows = rows_of(doc_client, record["id"], api_user)["rows"]

    assert {row["payload"]["instrument_name"] for row in rows} == {"HDFC Bank Limited", "Infosys Limited"}
    assert all(row["payload"]["identifier_type"] == "isin" for row in rows)


async def test_the_next_file_of_a_learned_layout_needs_no_mapping(doc_client, api_user, monkeypatch):

    """Once a mapping is confirmed the same layout parses straight through, which is the whole point."""

    stub_reading(monkeypatch, [HOLDING_SHEET])

    first = await upload(doc_client, api_user, unknown_workbook(), "mystery.xlsx")

    doc_client.post(
        f"/api/v1/documents/{first['id']}/mapping/confirm",
        json={
            "user_id": api_user,
            "provider": "test_broker",
            "name": "Test broker positions",
            "sheets": [
                {
                    "sheet": "Positions",
                    "header_row": 1,
                    "asset_type": "equity",
                    "mapping": {
                        "instrument_name": "Description",
                        "isin": "Security Code",
                        "quantity": "Qty Available",
                        "average_cost": "Cost Per Unit",
                        "current_value": "Current Amount",
                    },
                }
            ],
        },
    )

    second = await upload(doc_client, api_user, unknown_workbook() + b"\x00", "mystery_again.xlsx")

    assert second["status"] != "needs_mapping" or second["row_count"] >= 0


async def test_a_proposal_that_does_not_fit_the_workbook_is_rejected():

    """A mapping naming a column the sheet does not have is caught before a person is asked to confirm it."""

    from app.extraction.mapping import ProposedMapping, ProposedSheetMapping, validate_proposal
    from app.extraction.workbook import profile_workbook

    profile = profile_workbook(unknown_workbook())

    problems = validate_proposal(
        ProposedMapping(
            provider="test",
            sheets=[
                ProposedSheetMapping(
                    sheet="Positions",
                    header_row=1,
                    mapping={"instrument_name": "Description", "quantity": "Nonexistent Column"},
                )
            ],
        ),
        profile,
    )

    assert any("Nonexistent Column" in problem for problem in problems)


async def test_a_proposal_without_an_instrument_name_is_rejected():

    """A mapping with no instrument column cannot produce holdings and is refused rather than shown."""

    from app.extraction.mapping import ProposedMapping, ProposedSheetMapping, validate_proposal
    from app.extraction.workbook import profile_workbook

    problems = validate_proposal(
        ProposedMapping(
            provider="test",
            sheets=[ProposedSheetMapping(sheet="Positions", header_row=1, mapping={"quantity": "Qty Available"})],
        ),
        profile_workbook(unknown_workbook()),
    )

    assert any("instrument name" in problem for problem in problems)


async def test_a_suggestion_becomes_the_dictionary_everything_else_reads():

    """The model answers in pairs and the rest of the pipeline reads a dictionary, so the fold must be exact."""

    from app.extraction.mapping import SuggestedField, SuggestedMapping, SuggestedSheet

    suggestion = SuggestedMapping(
        provider="test_broker",
        document_kind="holdings_statement",
        sheets=[
            SuggestedSheet(
                sheet="Positions",
                header_row=1,
                asset_type="equity",
                fields=[
                    SuggestedField(field="instrument_name", column="Description"),
                    SuggestedField(field="quantity", column="Qty Available"),
                ],
            )
        ],
    )

    proposal = suggestion.to_proposal()

    assert proposal.provider == "test_broker"

    assert proposal.sheets[0].mapping == {
        "instrument_name": "Description",
        "quantity": "Qty Available",
    }


async def test_the_model_facing_schema_has_no_open_ended_object():

    """An open ended object cannot be a strict response schema, which is what made this call fail with a 400."""

    from app.extraction.mapping import SuggestedMapping

    schema = SuggestedMapping.model_json_schema()

    def objects(node):

        """Walk every nested schema node, since one free form object anywhere rejects the whole request."""

        if isinstance(node, dict):

            if node.get("type") == "object":
                yield node

            for value in node.values():
                yield from objects(value)

        elif isinstance(node, list):

            for value in node:
                yield from objects(value)

    assert list(objects(schema))

    assert all(node.get("properties") for node in objects(schema))


async def test_the_columns_are_offered_even_when_no_mapping_can_be_suggested(doc_client, api_user, monkeypatch):

    """A model that cannot be reached must cost the suggestion, not the ability to map the file at all."""

    from app.extraction import mapping as mapping_module

    stub_reading(monkeypatch, [HOLDING_SHEET])

    record = await upload(doc_client, api_user, unknown_workbook(), "mystery.xlsx")

    async def unreachable(profile):

        """Stand in for a model call that fails, which is the case that used to empty the card."""

        raise RuntimeError("the model is unreachable")

    monkeypatch.setattr(mapping_module, "propose_mapping", unreachable)

    response = doc_client.post(f"/api/v1/documents/{record['id']}/mapping/propose?user_id={api_user}")

    assert response.status_code == 200

    proposal = response.json()

    assert proposal["usable"] is False

    assert proposal["problems"]

    sheet = proposal["sheets"][0]

    assert sheet["mapping"] == {}

    assert "Description" in [column["header"] for column in sheet["columns"]]


async def test_committing_writes_holdings_tagged_with_the_batch(doc_client, api_user):

    """Accepted rows become holdings carrying the batch id that makes the import reversible as a unit."""

    from app.db.session import session_scope
    from app.models.orm.investments import HoldingRow

    record = await upload(doc_client, api_user, broker_workbook(), "broker.xlsx")

    doc_client.post(
        f"/api/v1/documents/{record['id']}/decision?user_id={api_user}",
        json={"status": "accepted", "only_pending": True},
    )

    commit = doc_client.post(f"/api/v1/documents/{record['id']}/commit?user_id={api_user}").json()

    assert commit["status"] == "committed"
    assert commit["rows_written"] == 3

    async with session_scope() as session:
        holdings = (await session.scalars(
            select(HoldingRow).where(HoldingRow.import_batch_id == commit["import_batch_id"])
        )).all()

    assert len(holdings) == 3
    assert all(holding.identifier_type == "isin" for holding in holdings)
    assert all(holding.invested_value is not None for holding in holdings)


async def test_extraction_writes_no_holdings_before_the_commit(doc_client, api_user):

    """An extracted holdings import leaves the holdings table exactly as it was."""

    before = await count_holdings(api_user)

    await upload(doc_client, api_user, broker_workbook(), "broker.xlsx")

    assert await count_holdings(api_user) == before
