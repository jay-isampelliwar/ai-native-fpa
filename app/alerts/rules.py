"""The alert rules, each one a pure function over already fetched records and computed figures.

An alert is a claim about someone's money made without them asking, which makes it the easiest
place in the product to lose trust. Every rule here therefore returns evidence and a calculator
version alongside its message, and none of them phrase a finding more strongly than the data
supports.

Rules are pure. They take a snapshot and return findings, with no repository access of their own,
so the same set of records produces the same alerts every time and a rule can be tested against a
fixture rather than against a database. Fetching happens once, in the service, which is also what
stops six rules issuing six versions of the same query.

Thresholds are constants at the top rather than inline numbers. They are product decisions - fifty
percent of income going to EMIs is a judgement, not a fact - and keeping them named and visible is
what lets them be argued with and tuned.

Severity is about what the user should do, not about how large the number is. ``action`` means
something will go wrong without a decision; ``attention`` means it is worth knowing; ``info`` is
context. A maturing deposit is an action because the money moves whether or not anyone chooses.

Nothing here writes, notifies or schedules. Rules produce findings; the service collects them; a
delivery layer decides what to do with them. That separation is why adding email later touches one
file.
"""

from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel, Field

from app.calculations.cashflow.v1 import CALCULATOR_VERSION as CASHFLOW_VERSION
from app.calculations.cashflow.v1 import CashflowResult
from app.calculations.goals.v1 import CALCULATOR_VERSION as GOALS_VERSION
from app.calculations.goals.v1 import GoalInput, run_goal_projection
from app.models.finance import CashflowRecords
from app.repositories.goals_repository import GoalSnapshot
from app.ui.builders import rupees

EMI_LOAD_THRESHOLD = Decimal("0.50")
LOW_SAVINGS_RATE = Decimal("10")
MATURITY_WINDOW_DAYS = 45
SIP_DEBIT_WINDOW_DAYS = 7


class Alert(BaseModel):

    """One finding the system raised without being asked, carrying what it was based on."""

    model_config = {"arbitrary_types_allowed": True}

    kind: str
    severity: str
    title: str
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)
    calculator_versions: list[str] = Field(default_factory=list)


class AlertContext(BaseModel):

    """Everything the rules read, fetched once so six rules do not issue six sets of queries."""

    model_config = {"arbitrary_types_allowed": True}

    as_of: date
    records: CashflowRecords
    cashflow: CashflowResult
    goals: list[GoalSnapshot] = Field(default_factory=list)
    maturing_deposits: list[dict] = Field(default_factory=list)


def cash_shortfall(context: AlertContext) -> list[Alert]:

    """Raise when committed outflow exceeds income, which is the finding that cannot wait."""

    if context.cashflow.free_surplus >= Decimal("0"):
        return []

    return [
        Alert(
            kind="cash_shortfall",
            severity="action",
            title="This month runs at a deficit",
            detail=(
                f"Income is {rupees(context.cashflow.total_income)} and committed outflow is "
                f"{rupees(context.cashflow.committed_outflow)}, leaving "
                f"{rupees(context.cashflow.free_surplus)}."
            ),
            evidence_ids=context.records.evidence_ids,
            calculator_versions=[CASHFLOW_VERSION],
        )
    ]


def heavy_emi_load(context: AlertContext) -> list[Alert]:

    """Raise when repayments take more than half of income, which leaves nothing to absorb a shock."""

    income = context.cashflow.total_income

    if income <= Decimal("0") or context.cashflow.total_emis <= income * EMI_LOAD_THRESHOLD:
        return []

    return [
        Alert(
            kind="heavy_emi_load",
            severity="attention",
            title="EMIs take more than half your income",
            detail=(
                f"{rupees(context.cashflow.total_emis)} of {rupees(income)} goes to repayments, "
                "which leaves little room if income pauses."
            ),
            evidence_ids=[record.id for record in context.records.emis],
            calculator_versions=[CASHFLOW_VERSION],
        )
    ]


def low_savings_rate(context: AlertContext) -> list[Alert]:

    """Raise when a positive month still saves almost nothing, which a surplus figure alone hides."""

    if context.cashflow.free_surplus < Decimal("0"):
        return []

    if context.cashflow.savings_rate_percent >= LOW_SAVINGS_RATE:
        return []

    return [
        Alert(
            kind="low_savings_rate",
            severity="attention",
            title="Very little is being saved",
            detail=(
                f"Your savings rate is {context.cashflow.savings_rate_percent}%, so most of what "
                "arrives is already committed."
            ),
            evidence_ids=context.records.evidence_ids,
            calculator_versions=[CASHFLOW_VERSION],
        )
    ]


def goal_drift(context: AlertContext) -> list[Alert]:

    """Raise for each goal whose required contribution has drifted past what is actually spare."""

    alerts: list[Alert] = []

    for snapshot in context.goals:

        projection = run_goal_projection(
            GoalInput(
                target_amount=snapshot.target_amount,
                target_date=snapshot.target_date,
                as_of=context.as_of,
                current_corpus=snapshot.funded_corpus,
                monthly_contribution=snapshot.monthly_contribution,
                inflation_percent=snapshot.inflation_percent,
            )
        )

        if projection.on_track:
            continue

        if projection.required_monthly <= context.cashflow.investable_surplus:
            continue

        alerts.append(
            Alert(
                kind="goal_drift",
                severity="attention",
                title=f"{snapshot.label} is drifting out of reach",
                detail=(
                    f"Closing the gap now needs {rupees(projection.required_monthly)} a month, "
                    f"against an investable surplus of {rupees(context.cashflow.investable_surplus)}."
                ),
                evidence_ids=snapshot.evidence_ids,
                calculator_versions=[GOALS_VERSION, CASHFLOW_VERSION],
            )
        )

    return alerts


def unfunded_goal(context: AlertContext) -> list[Alert]:

    """Raise for a goal nothing is paying into, which no projection will ever call on track."""

    return [
        Alert(
            kind="unfunded_goal",
            severity="attention",
            title=f"Nothing is funding {snapshot.label}",
            detail="This goal has no linked assets and no monthly contribution.",
            evidence_ids=snapshot.evidence_ids,
        )
        for snapshot in context.goals
        if snapshot.funded_corpus <= Decimal("0") and snapshot.monthly_contribution <= Decimal("0")
    ]


def maturing_deposits(context: AlertContext) -> list[Alert]:

    """Raise for deposits maturing soon, because that money moves whether or not anyone decides."""

    return [
        Alert(
            kind="deposit_maturing",
            severity="action",
            title=f"{deposit['institution']} deposit matures on {deposit['matures_on']}",
            detail="Decide where this goes before it renews at whatever rate is current.",
            evidence_ids=[deposit["id"]],
        )
        for deposit in context.maturing_deposits
    ]


def sip_debit_at_risk(context: AlertContext) -> list[Alert]:

    """Raise when an SIP debits soon and the surplus will not cover it, which is a bounce waiting to happen."""

    horizon = context.as_of + timedelta(days=SIP_DEBIT_WINDOW_DAYS)

    alerts: list[Alert] = []

    for sip in context.records.sips:

        if sip.next_debit_on is None or not (context.as_of <= sip.next_debit_on <= horizon):
            continue

        if context.cashflow.free_surplus >= sip.amount:
            continue

        alerts.append(
            Alert(
                kind="sip_debit_at_risk",
                severity="action",
                title=f"{sip.scheme_name} debits on {sip.next_debit_on}",
                detail=(
                    f"The debit is {rupees(sip.amount)} and this month's free surplus is "
                    f"{rupees(context.cashflow.free_surplus)}."
                ),
                evidence_ids=[sip.id],
                calculator_versions=[CASHFLOW_VERSION],
            )
        )

    return alerts


RULES = [
    cash_shortfall,
    heavy_emi_load,
    low_savings_rate,
    goal_drift,
    unfunded_goal,
    maturing_deposits,
    sip_debit_at_risk,
]

SEVERITY_ORDER = {"action": 0, "attention": 1, "info": 2}
