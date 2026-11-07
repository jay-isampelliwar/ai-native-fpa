"""Tests for the units a holding has after its invested amount or current value changes without units."""

from decimal import Decimal

import pytest

from app.db.enums import HoldingAssetType
from app.features.investments.service import Instrument, units_after
from app.features.records.exceptions import RecordError


FUND = Instrument(HoldingAssetType.mutual_fund, 1, "INF846K01EW2", "Axis Liquid Fund", Decimal("3187.2399"), None)

STOCK = Instrument(HoldingAssetType.stock, 2, "INE003A01024", "Siemens Energy India", Decimal("2846.60"), None)


def test_more_money_buys_more_units_at_the_latest_nav() -> None:

    """Raising the invested amount from 1,00,000 to 1,70,000 adds the units 70,000 buys at today's NAV, rounded down to three decimals."""

    units = units_after(FUND, Decimal("31.375"), Decimal("100000"), {"invested_amount": 170000})

    assert units == Decimal("53.337")


def test_current_value_sets_the_units_outright() -> None:

    """Telling the app what the holding is worth now sets units to value over NAV."""

    assert units_after(FUND, Decimal("31.375"), Decimal("100000"), {"current_value": 170700}) == Decimal("53.557")


def test_same_amount_or_unknown_old_amount_leaves_units_alone() -> None:

    """No change in money, or no old amount to compare with, keeps the units as they are."""

    assert units_after(FUND, Decimal("31.375"), Decimal("100000"), {"invested_amount": 100000}) is None
    assert units_after(FUND, Decimal("31.375"), None, {"invested_amount": 170000}) is None
    assert units_after(FUND, Decimal("31.375"), Decimal("100000"), {"folio_number": "123"}) is None


def test_stock_units_stay_whole_and_cannot_reach_zero() -> None:

    """A stock gains whole shares only, and taking out more than it holds is refused."""

    assert units_after(STOCK, Decimal("3"), Decimal("10300"), {"invested_amount": 16000}) == Decimal("5")

    with pytest.raises(RecordError):
        units_after(STOCK, Decimal("3"), Decimal("10300"), {"invested_amount": 100})


def test_missing_price_is_refused() -> None:

    """Without a latest price the units cannot be worked out, so the change is refused with a clear message."""

    unpriced = Instrument(HoldingAssetType.mutual_fund, 3, "INF000000000", "No Price Fund", None, None)

    with pytest.raises(RecordError):
        units_after(unpriced, Decimal("10"), Decimal("1000"), {"invested_amount": 2000})
