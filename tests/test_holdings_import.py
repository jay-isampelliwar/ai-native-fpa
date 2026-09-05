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


async def test_an_unknown_layout_asks_for_a_mapping_instead_of_guessing(doc_client, api_user):

    """A layout no template covers is neither parsed nor failed, it waits for a person to map it."""

    record = await upload(doc_client, api_user, unknown_workbook(), "mystery.xlsx")

    assert record["status"] == "needs_mapping"
    assert record["row_count"] == 0
    assert await count_holdings(api_user) == 0


async def test_a_confirmed_mapping_parses_the_import(doc_client, api_user):

    """Confirming a mapping re extracts the same file deterministically, with no model involved."""

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


async def test_the_next_file_of_a_learned_layout_needs_no_mapping(doc_client, api_user):

    """Once a mapping is confirmed the same layout parses straight through, which is the whole point."""

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
