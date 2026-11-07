"""Tests for the overview maths on plain rows, and the shape of every overview card, with no database."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace as Row

import pytest

from app.agent.blocks import (
    asset_split_block,
    cash_flow_block,
    changes_block,
    checklist_block,
    compare_block,
    empty_block,
    health_block,
    month_summary_block,
    net_worth_block,
    plain_receipt,
    receipt_block,
    timeline_block,
    )
from app.agent.cards import Described
from app.db.enums import GoalStatus, LoanType, PhysicalAssetType, TransactionDirection
from app.db.models import Loan
from app.features.overview.service import (
    MonthFlow,
    MonthSummary,
    events_from,
    health_from,
    history_from,
    net_worth_from,
    next_monthly,
    )
from app.features.records.kinds import RecordKind


TODAY = date(2026, 11, 7)


def worth_rows():

    """A small saved life: one account, one FD, one EPF, a flat and gold, two holdings, one loan and one card."""

    return net_worth_from(
        [Row(balance=Decimal("184000"))],
        [Row(principal=Decimal("200000"))],
        [Row(balance=Decimal("1480000"))],
        [Row(asset_type=PhysicalAssetType.real_estate, current_value=Decimal("3800000")), Row(asset_type=PhysicalAssetType.gold, current_value=Decimal("150000"))],
        [(Decimal("109996.45"), Decimal("110000")), (Decimal("99999.30"), Decimal("100000"))],
        [Row(outstanding=Decimal("4230000"))],
        [Row(outstanding=Decimal("31000"))],
        )


def test_net_worth_adds_what_is_owned_and_takes_off_what_is_owed() -> None:

    """Assets, owed and net worth add up, and the split lists only non-empty types, largest first."""

    worth = worth_rows()

    assert worth.assets == Decimal("6023995.75")
    assert worth.owed == Decimal("4261000")
    assert worth.value == Decimal("1762995.75")
    assert worth.invested == Decimal("210000")
    assert [label for label, _ in worth.split] == ["Property", "EPF, PPF & NPS", "Bank & FDs", "Stocks & funds", "Other assets"]


def test_net_worth_and_split_cards() -> None:

    """The hero card carries the four facts, and the ring's shares add up to 100."""

    worth = worth_rows()

    hero = net_worth_block(worth, TODAY)

    assert hero["type"] == "hero" and hero["tone"] == "up" and hero["value"] == "₹17,62,996"
    assert [fact["label"] for fact in hero["facts"]] == ["Assets", "Loans & dues", "Invested", "In the bank"]
    assert hero["as_of"] == "7 Nov 2026"

    ring = asset_split_block(worth)

    assert ring is not None and ring["type"] == "ring" and ring["total"] == "₹60,23,996"
    assert round(sum(item["pct"] for item in ring["items"]), 1) == 100.0
    assert ring["items"][0] == {"label": "Property", "value": "₹38,00,000", "pct": 63.08}


def test_health_score_and_gauge_card() -> None:

    """Each check earns up to 25: a full emergency fund and low debt score full, a thin cover scores partly."""

    health = health_from(income=112000, spending=64300, emis=12100, card_dues=0, cash=400000, life_cover=5000000)

    points = {check.label: round(check.points, 1) for check in health.checks}

    assert points["Emergency fund"] == 25.0
    assert points["Debt to income"] == 25.0
    assert points["Savings rate"] == 25.0
    assert points["Life cover"] == 9.3
    assert health.score == 84 and health.verdict == "Strong"
    assert [check.tone for check in health.checks] == ["up", "up", "up", "warn"]

    card = health_block(health, TODAY)

    assert card["type"] == "gauge" and card["score"] == 84 and card["verdict"] == "Strong"
    assert card["checks"][3]["tone"] == "warn" and card["checks"][3]["value"].startswith("₹50,00,000")


@pytest.mark.parametrize(
    ("income", "spending", "emis", "dues", "cash", "cover", "score", "verdict"),
    [
        (100000, 100000, 30000, 30000, 0, 0, 0, "At risk"),
        (100000, 70000, 45000, 0, 210000, 0, 25 + 0 + 25 + 0, "Weak"),
        (100000, 40000, 30000, 0, 240000, 12000000, 100, "Strong"),
        ],
    )
def test_health_score_edges(
    income: int,
    spending: int,
    emis: int,
    dues: int,
    cash: int,
    cover: int,
    score: int,
    verdict: str,
    ) -> None:

    """Nothing saved scores zero, 45% debt scores nothing on that check, and a full life scores 100."""

    health = health_from(income, spending, emis, dues, cash, cover)

    assert (health.score, health.verdict) == (score, verdict)


def test_history_groups_transactions_by_month_and_kpis_carry_a_trend() -> None:

    """Six months come back oldest first with inflow and outflow, and the tiles get a change and trend from them."""

    rows = [
        Row(txn_date=date(2026, 11, 3), direction=TransactionDirection.inflow, amount=Decimal("112000")),
        Row(txn_date=date(2026, 11, 4), direction=TransactionDirection.outflow, amount=Decimal("640")),
        Row(txn_date=date(2026, 10, 1), direction=TransactionDirection.inflow, amount=Decimal("112000")),
        Row(txn_date=date(2026, 10, 9), direction=TransactionDirection.outflow, amount=Decimal("70000")),
        Row(txn_date=date(2025, 1, 1), direction=TransactionDirection.inflow, amount=Decimal("999")),
        ]

    history = history_from(rows, TODAY)

    assert [flow.month for flow in history] == [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)]
    assert (history[-1].income, history[-1].spending, history[-2].spending) == (Decimal("112000"), Decimal("640"), Decimal("70000"))
    assert history_from([], TODAY) == []

    summary = MonthSummary(112000, 64300, history)

    kpis = month_summary_block(summary, TODAY)

    assert kpis["type"] == "kpis" and [item["label"] for item in kpis["items"]] == ["Income", "Spending", "Saved"]
    assert kpis["items"][2]["value"] == "₹47,700"
    assert kpis["items"][1]["change"] == {"text": "−₹69,360 (99.1%)", "direction": "down"}
    assert len(kpis["items"][0]["trend"]) == 6

    bars = cash_flow_block(summary)

    assert bars is not None and bars["labels"] == ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]
    assert bars["series"][1]["values"][-1] == 640.0
    assert cash_flow_block(MonthSummary(1, 1, [])) is None

    flat = month_summary_block(MonthSummary(112000, 64300, []), TODAY)

    assert "change" not in flat["items"][0] and "trend" not in flat["items"][0]


def test_upcoming_events_sort_by_date_then_goals() -> None:

    """A SIP, an EMI, a card due, a maturing FD and a renewal in the window, soonest first, then the goal by year."""

    sips = [(Row(is_active=True, sip_day=10, amount=Decimal("10000")), "Parag Parikh Flexi Cap"), (Row(is_active=False, sip_day=1, amount=Decimal("1")), "Old")]
    loans = [Row(start_date=date(2024, 3, 5), lender="Axis Bank", emi=Decimal("12100"))]
    cards = [Row(due_day=18, bank_name="HDFC", outstanding=Decimal("31000")), Row(due_day=None, bank_name="SBI", outstanding=Decimal("0"))]
    deposits = [Row(maturity_date=date(2026, 11, 30), bank_name="SBI", maturity_amount=Decimal("212000"), principal=Decimal("200000")), Row(maturity_date=date(2027, 5, 1), bank_name="Far", maturity_amount=None, principal=Decimal("1"))]
    policies = [Row(renewal_date=date(2026, 11, 20), insurer="HDFC Life", premium=Decimal("18000"))]
    goals = [Row(status=GoalStatus.active, target_year=2029, name="House", target_amount=Decimal("3000000")), Row(status=GoalStatus.dropped, target_year=2027, name="Bike", target_amount=Decimal("1"))]

    events = events_from(TODAY, sips, loans, cards, deposits, policies, goals)

    assert [event.label for event in events] == [
        "EMI · Axis Bank",
        "SIP · Parag Parikh Flexi Cap",
        "Card due · HDFC",
        "Renewal · HDFC Life",
        "FD matures · SBI",
        "Goal · House",
        ]
    assert [event.state for event in events] == ["past", "soon", "far", "far", "far", "far"]
    assert events[0].when == "5 Nov" and events[-1].when == "2029"

    card = timeline_block(events)

    assert card is not None and card["type"] == "timeline" and card["items"][1] == {"when": "10 Nov", "label": "SIP · Parag Parikh Flexi Cap", "value": "₹10,000", "state": "soon"}
    assert timeline_block([]) is None


def test_monthly_events_roll_to_next_month_when_long_past() -> None:

    """A day more than a week gone this month moves to next month; a day in the last week stays as past."""

    assert next_monthly(5, date(2026, 11, 25)) == date(2026, 12, 5)
    assert next_monthly(20, date(2026, 11, 25)) == date(2026, 11, 20)
    assert next_monthly(31, date(2026, 11, 2)) == date(2026, 11, 30)


def test_receipt_changes_checklist_compare_and_empty_cards() -> None:

    """The receipt names the loan with its facts, changes show old beside new, the checklist counts done, and the empty card offers the form."""

    loan = Loan(id=18, loan_type=LoanType.car, lender="Axis Bank", principal=Decimal("500000"), outstanding=Decimal("310000"), interest_rate=Decimal("9.4"), emi=Decimal("12100"), start_date=date(2024, 3, 5), end_date=date(2029, 3, 5))

    receipt = receipt_block("saved", loan)

    assert receipt is not None and receipt["type"] == "receipt" and receipt["action"] == "saved"
    assert (receipt["kind"], receipt["name"], receipt["record_id"]) == ("Loan", "Axis Bank", 18)
    assert receipt["facts"][0]["label"] == "Principal" or receipt["facts"][0]["value"].startswith("₹")

    profile = plain_receipt("saved", "Profile", "Your details", {"city": "Chandrapur"})

    assert profile["facts"] == [{"label": "City", "value": "Chandrapur"}]

    changes = changes_block(Described(name="Axis Bank", thing="Axis Bank loan"), {"emi": "₹12,100"}, {"emi": "₹11,500"}, TODAY)

    assert changes == {
        "type": "changes",
        "title": "Updated · Axis Bank",
        "fields": [{"label": "EMI", "old": "₹12,100", "new": "₹11,500"}],
        "note": "1 field changed · 7 Nov 2026",
        }

    checklist = checklist_block({"profile": "provided", "income": "pending", "loans": "none", "insurance": "declined"})

    assert checklist["subtitle"] == "2 of 4 done"
    assert [item["status"] for item in checklist["items"]] == ["done", "missing", "done", "declined"]
    assert checklist["items"][0]["label"] == "Your details"

    empty = empty_block(RecordKind.loans)

    assert empty == {"type": "empty", "title": "No loans saved yet", "text": "Tell me about your loans in the chat, or open the form.", "form": "loan"}
    assert empty_block(RecordKind.credit_cards)["form"] is None

    compare = compare_block({
        "funds": [
            {"scheme": "Parag Parikh Flexi Cap Fund - Direct Plan", "category": "equity", "sub_category": "flexi_cap", "nav": 84.12, "equity_holdings": 42, "asset_split_pct": {"equity": 78.5, "debt": 10.0}, "sector_split": [{"sector": "financial_services", "weight_pct": 31.2}]},
            {"scheme": "HDFC Flexi Cap Fund", "category": "equity", "sub_category": "flexi_cap", "nav": 1912.4, "equity_holdings": 55, "asset_split_pct": {"equity": 95.0}, "sector_split": []},
            ],
        "overlap": [{"funds": ["Parag Parikh Flexi Cap Fund - Direct Plan", "HDFC Flexi Cap Fund"], "common_stocks": 11, "overlap_pct": 23.4}],
        })

    assert compare["type"] == "compare" and compare["columns"] == ["Parag Parikh Flexi Cap Fund", "HDFC Flexi Cap Fund"]
    assert [row["label"] for row in compare["rows"]] == ["Category", "NAV", "Stocks held", "Equity", "Debt", "Top sector"]
    assert compare["rows"][4]["values"] == ["10%", "—"] and compare["rows"][5]["values"] == ["Financial services", "—"]
    assert compare["note"].endswith("11 stocks in common, 23.4% overlap")
