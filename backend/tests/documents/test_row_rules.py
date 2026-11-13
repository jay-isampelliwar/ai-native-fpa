"""Tests for the plain row checks, the questions, and the name ranking used to match stocks and funds."""

from datetime import date
from decimal import Decimal

from app.features.documents.matching import plan_wanted, rank, search_words, starts_a_word, symbol_forms
from app.features.documents.records import same
from app.features.documents.rules import (
    keep_answers,
    mismatch_question,
    open_count,
    option,
    question,
    required_errors,
    value_errors,
    )


def test_missing_needed_fields_are_errors() -> None:

    """An FD with no rate or dates gets one error per missing field."""

    errors = required_errors("fixed_deposits", {"bank_name": "SBI", "deposit_type": "fd", "principal": "10000.00"})

    assert [error.split(":")[0] for error in errors] == ["interest_rate", "start_date", "maturity_date"]


def test_value_limits() -> None:

    """Units must be above zero, balances cannot be negative, and rates and SIP days stay in range."""

    errors = value_errors({"units": "0.0000", "balance": "-5.00", "interest_rate": "85.00", "sip_day": 31})

    assert {error.split(":")[0] for error in errors} == {"units", "balance", "interest_rate", "sip_day"}
    assert value_errors({"units": "10.0000", "interest_rate": "8.50", "sip_day": 5}) == []


def test_mismatch_asks_only_past_one_percent() -> None:

    """Units times price off by more than 1% raises a question with both values as choices."""

    close = {"units": "10.0000", "current_price": "100.0000", "current_value": "1005.00"}
    far = {"units": "10.0000", "current_price": "100.0000", "current_value": "1500.00"}

    assert mismatch_question(3, close) is None

    item = mismatch_question(3, far)

    assert item["kind"] == "value_mismatch"
    assert [choice["value"] for choice in item["options"]] == ["1500.00", "1000.00"]


def test_answers_carry_over_only_when_still_offered() -> None:

    """An earlier answer stays on the same question, but is dropped when its choice is gone."""

    old = [{**question("q1", "pick", "?", [option("a", "A")]), "answer": "a"}]
    still = keep_answers([question("q1", "pick", "?", [option("a", "A"), option("b", "B")])], old)
    gone = keep_answers([question("q1", "pick", "?", [option("b", "B")])], old)

    assert still[0]["answer"] == "a"
    assert gone[0]["answer"] is None
    assert open_count(gone) == 1


def test_symbol_forms_drop_exchange_suffix() -> None:

    """GOLDBEES-E is also tried as GOLDBEES."""

    assert symbol_forms("GOLDBEES-E") == ["GOLDBEES-E", "GOLDBEES"]
    assert symbol_forms("TCS") == ["TCS"]


def test_search_words_skip_plan_words() -> None:

    """Plan words such as direct and growth are not searched on."""

    assert search_words("HDFC Small Cap Fund - Direct Plan - Growth") == ["hdfc", "small", "cap"]


def test_plan_wanted() -> None:

    """The plan and option come from the name or hint, or stay unknown."""

    assert plan_wanted("HDFC Small Direct Growth") == ("direct", "growth")
    assert plan_wanted("SBI Mid cap Regular Growth") == ("regular", "growth")
    assert plan_wanted("SBI Mid cap") == (None, None)


def test_rank_puts_matching_plan_first() -> None:

    """Among plans of one scheme, the one fitting 'Direct Growth' ranks first."""

    plans = [
        {"kind": "fund", "id": 1, "name": "HDFC Small Cap Fund - Regular Plan - Growth", "plan_type": "regular", "option_type": "growth"},
        {"kind": "fund", "id": 2, "name": "HDFC Small Cap Fund - Direct Plan - IDCW", "plan_type": "direct", "option_type": "idcw"},
        {"kind": "fund", "id": 3, "name": "HDFC Small Cap Fund - Direct Plan - Growth", "plan_type": "direct", "option_type": "growth"},
        ]

    assert [plan["id"] for plan in rank("HDFC Small Direct Growth", "Direct Growth", plans)] == [3, 2, 1]


def test_same_compares_across_forms() -> None:

    """Saved values and parsed text compare equal across Decimal, date, enum-like text and case."""

    assert same(Decimal("100.5"), "100.50")
    assert same(date(2026, 10, 1), "2026-10-01")
    assert same("Rent / Maintenance", "rent / maintenance")
    assert not same(Decimal("100"), "101.00")


def test_rank_ignores_bracket_notes() -> None:

    """A renamed fund with an '(erstwhile ...)' note still ranks above a fund with an extra word in its name."""

    plans = [
        {"kind": "fund", "id": 1, "name": "ICICI Prudential Large & Mid Cap Fund - Direct Plan - Growth", "plan_type": "direct", "option_type": "growth"},
        {"kind": "fund", "id": 2, "name": "ICICI Prudential Large Cap Fund (erstwhile Bluechip Fund) - Direct Plan - Growth", "plan_type": "direct", "option_type": "growth"},
        ]

    assert rank("ICICI Prudential Large Cap Fund Direct Growth", "", plans)[0]["id"] == 2


def test_search_word_must_start_a_word() -> None:

    """'uti' matches UTI funds, not the 'uti' inside 'distribution'."""

    assert starts_a_word("uti", "UTI Nifty 50 Index Fund")
    assert not starts_a_word("uti", "SBI Fund - Income Distribution Option")
