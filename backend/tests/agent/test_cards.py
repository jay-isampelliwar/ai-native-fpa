"""Tests for the plain-words pieces of approval cards, built from unsaved models so no database is needed."""

from datetime import date
from decimal import Decimal

import pytest

from app.agent.approval import real_changes
from app.agent.cards import change_title, generic_describe, remove_note, remove_title, rupees, show
from app.db.enums import ExpenseCategory, FamilyRelation, LoanType, PaymentFrequency, RetirementAccountType
from app.db.models import Expense, FamilyMember, Holding, Loan, RetirementAccount, SipPlan
from app.features.records.kinds import RecordKind


@pytest.mark.parametrize(
    ("value", "places", "text"),
    [
        (Decimal("5000"), 0, "₹5,000"),
        (Decimal("120000"), 0, "₹1,20,000"),
        (Decimal("12345678"), 0, "₹1,23,45,678"),
        (Decimal("90.7043"), 2, "₹90.70"),
        (Decimal("250.00"), 2, "₹250"),
        (Decimal("999"), 0, "₹999"),
        ],
    )
def test_rupees_use_indian_commas(value: Decimal, places: int, text: str) -> None:

    """Lakhs and crores get Indian commas, and zero paise are left out."""

    assert rupees(value, places) == text


def test_values_read_like_a_person_writes_them() -> None:

    """Money, rates, dates, units, Yes or No, and plain enum words."""

    assert show(Holding, "invested_amount", Decimal("50000.00")) == "₹50,000"
    assert show(Holding, "units", Decimal("551.2410")) == "551.241"
    assert show(Holding, "avg_buy_price", Decimal("90.7044")) == "₹90.70"
    assert show(Loan, "interest_rate", Decimal("8.50")) == "8.5%"
    assert show(Loan, "start_date", date(2026, 11, 4)) == "4 Nov 2026"
    assert show(SipPlan, "is_active", True) == "Yes"
    assert show(SipPlan, "sip_day", 5) == "5th of every month"
    assert show(Expense, "frequency", PaymentFrequency.half_yearly) == "Half yearly"
    assert show(Expense, "amount", None) == "Not set"


def test_a_named_item_is_called_by_its_name_and_kind() -> None:

    """An expense called Rent reads as "Rent expense", with its category as a label and no raw fields."""

    rent = Expense(category=ExpenseCategory.rent, name="Rent", amount=Decimal("20000"), frequency=PaymentFrequency.monthly, is_essential=True)

    described = generic_describe(RecordKind.expenses, rent)

    assert described.thing == "Rent expense"
    assert change_title(RecordKind.expenses, described) == "Change your Rent expense?"
    assert remove_title(described) == "Remove Rent expense from your list?"
    assert described.chips == ["Rent"]
    assert described.facts[0] == {"label": "Amount", "value": "₹20,000"}


def test_a_lender_names_a_loan() -> None:

    """A loan is named by its lender, such as "HDFC loan", with its type as a label."""

    loan = Loan(loan_type=LoanType.home, lender="HDFC", principal=Decimal("4000000"), outstanding=Decimal("3200000"))

    described = generic_describe(RecordKind.loans, loan)

    assert described.thing == "HDFC loan"
    assert described.chips == ["Home"]
    assert {"label": "Still to pay", "value": "₹32,00,000"} in described.facts


def test_an_item_without_a_name_is_named_by_its_type() -> None:

    """A retirement account has no name field, so it reads as "EPF retirement account"."""

    epf = RetirementAccount(account_type=RetirementAccountType.epf, balance=Decimal("800000"), as_of_date=date(2026, 11, 1))

    assert generic_describe(RecordKind.retirement_accounts, epf).thing == "EPF retirement account"


def test_a_family_member_reads_by_name() -> None:

    """A family member's change card says "Change Aarav's details?"."""

    aarav = FamilyMember(name="Aarav", relation=FamilyRelation.child, is_dependent=True)

    assert change_title(RecordKind.family, generic_describe(RecordKind.family, aarav)) == "Change Aarav's details?"


def test_removing_a_holding_says_the_real_investment_is_not_sold() -> None:

    """The remove note for a holding calms the user: only Mosaic's copy goes."""

    assert "not sold" in remove_note(RecordKind.holdings)


def test_only_real_changes_count() -> None:

    """Fields whose new value equals the saved one are left out, and a change of nothing gives an empty result."""

    rent = Expense(category=ExpenseCategory.rent, name="Rent", amount=Decimal("20000.00"), frequency=PaymentFrequency.monthly, is_essential=True)

    assert real_changes(RecordKind.expenses, rent, {"amount": 25000, "name": "Rent"}) == {"amount": Decimal("25000")}
    assert real_changes(RecordKind.expenses, rent, {"amount": "20000"}) == {}
    assert real_changes(RecordKind.expenses, rent, {"user_id": 1}) is None


def test_holdings_card_sorts_by_value_and_adds_up_gain() -> None:

    """Holdings come biggest first with short names and shares, and the top row has value and overall gain."""

    from datetime import date
    from decimal import Decimal
    from types import SimpleNamespace

    from app.agent.blocks import records_block
    from app.features.records.kinds import RecordKind

    records = [
        SimpleNamespace(id=1, current_value=None, invested_amount=Decimal("6000")),
        SimpleNamespace(id=2, current_value=None, invested_amount=Decimal("110000")),
        ]

    named = {
        1: {"name": "BANDHAN SMALL CAP FUND - DIRECT PLAN GROWTH", "value_today": 5999.99, "nav_date": date(2026, 11, 3)},
        2: {"name": "Nippon India Growth Mid Cap Fund - Direct Plan", "value_today": 109996.45, "nav_date": date(2026, 11, 3)},
        }

    block = records_block(RecordKind.holdings, records, named, 2)

    assert block is not None and block["type"] == "holdings"
    assert [item["name"] for item in block["items"]] == ["Nippon India Growth Mid Cap Fund", "Bandhan Small Cap Fund"]
    assert [item["share"] for item in block["items"]] == [94.83, 5.17]
    assert block["summary"][1] == {"label": "Overall", "value": "−₹3.56", "note": "−0.00%", "direction": "down"}
    assert block["as_of"] == "3 Nov 2026"
