"""The portfolio read, which is the one endpoint an interface needs before it can show anything.

These tests exist because the endpoint shipped without them and failed on its first real request: the
asset type grouping type checked, passed review, and then raised a PostgreSQL grouping error the
moment a row existed. Nothing but an actual query against an actual database would have caught it.

``test_totals_and_grouping_survive_a_real_query`` is therefore the important one. It asserts figures,
but its real job is to execute the SQL - a repository whose queries are never run is a repository
whose queries are unverified.

Valuation dating is asserted because the honest claim matters. These figures are what a statement said
on the day it was exported and nothing refreshes them, so ``valued_at`` has to come back or an
interface would be free to imply the numbers are current.

Ownership is checked here as everywhere: another user's positions must not appear, and a user with
nothing gets an empty portfolio rather than someone else's.
"""

from decimal import Decimal

import pytest


@pytest.fixture
async def seeded_holdings(api_user):

    """Give the test user two positions of different asset types, as an import would."""

    from datetime import date

    from app.db.session import session_scope
    from app.models.finance import HoldingKind
    from app.repositories.records_repository import records_repository

    async with session_scope() as session:
        await records_repository.create_holding(
            session,
            user_id=api_user,
            kind=HoldingKind.STOCK,
            instrument_name="Test Equity",
            units=Decimal("100"),
            average_cost=Decimal("250.0000"),
            as_of=date(2026, 8, 25),
            isin="INE000A01001",
            asset_type="equity",
            identifier_type="isin",
            invested_value=Decimal("25000.00"),
            current_value=Decimal("31000.00"),
            import_batch_id="batch_test",
        )

        await records_repository.create_holding(
            session,
            user_id=api_user,
            kind=HoldingKind.MUTUAL_FUND,
            instrument_name="Test Fund",
            units=Decimal("500.500"),
            average_cost=Decimal("40.0000"),
            as_of=date(2026, 7, 21),
            asset_type="mutual_fund",
            identifier_type="scheme_folio",
            invested_value=Decimal("20020.00"),
            current_value=Decimal("18000.00"),
        )

    return api_user


async def test_totals_and_grouping_survive_a_real_query(seeded_holdings):

    """The summary executes against PostgreSQL and totals both positions, grouped by asset type."""

    from app.repositories.holdings_repository import holdings_repository

    summary = await holdings_repository.summary(seeded_holdings)

    assert summary.count == 2
    assert summary.invested_value == Decimal("45020.00")
    assert summary.current_value == Decimal("49000.00")
    assert summary.unrealised == Decimal("3980.00")
    assert set(summary.by_asset_type) == {"equity", "mutual_fund"}
    assert summary.by_asset_type["equity"] == Decimal("31000.00")


async def test_the_valuation_is_dated_by_the_newest_statement(seeded_holdings):

    """A portfolio says when it was last valued, so an interface cannot imply the figures are live."""

    from app.repositories.holdings_repository import holdings_repository

    summary = await holdings_repository.summary(seeded_holdings)

    assert summary.valued_at == "2026-08-25"


async def test_identifier_strength_is_reported(seeded_holdings):

    """How many positions are keyed on an ISIN is part of how much the portfolio can be trusted."""

    from app.repositories.holdings_repository import holdings_repository

    summary = await holdings_repository.summary(seeded_holdings)

    assert summary.identified_by_isin == 1


async def test_positions_are_ordered_by_what_they_are_worth(seeded_holdings):

    """The largest position leads, since a portfolio screen is read from the top."""

    from app.repositories.holdings_repository import holdings_repository

    summary = await holdings_repository.summary(seeded_holdings)

    assert [holding.instrument_name for holding in summary.holdings] == ["Test Equity", "Test Fund"]


async def test_another_users_portfolio_is_empty(seeded_holdings):

    """A user with no positions gets nothing rather than someone else's holdings."""

    from app.repositories.holdings_repository import holdings_repository

    summary = await holdings_repository.summary(999_999)

    assert summary.count == 0
    assert summary.holdings == []
    assert summary.valued_at is None


async def test_the_endpoint_returns_the_summary(api_user, seeded_holdings):

    """The HTTP surface returns what the repository computed, which is what the frontend consumes."""

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        body = client.get(f"/api/v1/assets/holdings?user_id={api_user}").json()

    assert body["count"] == 2
    assert body["valued_at"] == "2026-08-25"
    assert body["by_asset_type"]["equity"] == "31000.00"
