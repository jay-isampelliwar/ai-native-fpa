"""Tests for the write check that need no database: comparing saved values, the mismatch result, and the empty search refusal."""

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.agent.context import PlannerContext
from app.agent.tools.market import search_stocks_and_funds
from app.agent.tools.results import checked, mismatch, unverified
from app.agent.tools.verify import differences, same_value
from app.db.enums import HoldingAssetType
from app.db.models import Holding


def holding(**fields: object) -> Holding:

    """A holding row in memory only, for comparing values."""

    return Holding(**fields)


def test_numbers_match_after_rounding_to_the_column() -> None:

    """An asked 2170 equals a saved 2170.00, and an asked 0.12345 equals the saved 0.1235."""

    assert same_value(Decimal("2170.00"), 2170)
    assert same_value(Decimal("0.1235"), Decimal("0.12345"))


def test_a_different_number_does_not_match() -> None:

    """An asked 110000 does not equal a saved 6000."""

    assert not same_value(Decimal("6000.00"), Decimal("110000"))


def test_enums_and_dates_match_their_own_values() -> None:

    """An enum matches its value and a date matches the same date."""

    assert same_value(HoldingAssetType.mutual_fund, "mutual_fund")
    assert same_value(date(2026, 11, 5), date(2026, 11, 5))


def test_differences_lists_each_wrong_field_and_skips_non_columns() -> None:

    """A wrong fund id and amount are listed with both values, and a name that is not a column is skipped."""

    row = holding(mutual_fund_id=2275, units=Decimal("0"), invested_amount=Decimal("6000.00"))

    wrong = differences(row, {"mutual_fund_id": 1435, "invested_amount": 110000, "units": 0, "scheme_name": "Nippon"})

    assert wrong == {
        "mutual_fund_id": {"asked": "1435", "saved": "2275"},
        "invested_amount": {"asked": "110000", "saved": "6000"},
        }


def test_a_missing_saved_value_shows_as_not_set() -> None:

    """An asked folio number that was not saved shows as not set."""

    assert differences(holding(), {"folio_number": "123"}) == {"folio_number": {"asked": "123", "saved": "not set"}}


def test_checked_is_success_and_verified() -> None:

    """A checked save is success with verified true."""

    result = checked("Saved.", {"id": 1})

    assert result.status == "success"
    assert result.verified is True


def test_mismatch_and_unverified_are_not_success() -> None:

    """Both refusals carry the mismatch status and their own code."""

    assert mismatch({"units": {"asked": "5", "saved": "3"}}).error_code == "save_mismatch"
    assert unverified().error_code == "not_verified"
    assert unverified().status == "mismatch"


async def test_search_with_no_query_and_no_filter_is_refused() -> None:

    """An empty search asks for a query or a filter instead of reading the database."""

    runtime = SimpleNamespace(context=PlannerContext(user_id=1), tool_call_id="call_1", state=None)

    message = await search_stocks_and_funds.coroutine(runtime=runtime)

    result = json.loads(message.content)

    assert result["status"] == "validation_error"
    assert result["data"]["missing"] == ["query or filter"]
