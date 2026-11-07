"""The maths behind the overview cards as plain functions on simple rows, and the service that loads a user's rows and runs them."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.calc.cash_flow import MonthlyCashFlow
from app.calc.money import indian_number
from app.db.enums import GoalStatus, PhysicalAssetType, PolicyType, TransactionDirection
from app.db.models import (
    BankAccount,
    CreditCard,
    FixedDeposit,
    Goal,
    Holding,
    InsurancePolicy,
    Loan,
    PhysicalAsset,
    RetirementAccount,
    SipPlan,
    Transaction,
    )
from app.features.analysis.service import AnalysisService
from app.features.investments.market import MarketService
from app.features.records.base_repository import BaseUserRecordRepository


HISTORY_MONTHS = 6

EMERGENCY_MONTHS_FULL = 6.0

DEBT_RATIO_FULL = 0.30

DEBT_RATIO_ZERO = 0.60

SAVINGS_RATE_FULL = 0.30

COVER_MULTIPLE_FULL = 10.0

CHECK_POINTS = 25.0

SOON_DAYS = 7

PAST_DAYS = 7

AHEAD_DAYS = 30

MAX_EVENTS = 10

LIFE_POLICIES = (PolicyType.term, PolicyType.life)


@dataclass(frozen=True)
class NetWorth:

    """Everything the user owns and owes, added up, with the split of what they own."""

    cash: Decimal
    deposits: Decimal
    retirement: Decimal
    property: Decimal
    other_assets: Decimal
    investments: Decimal
    invested: Decimal
    loans: Decimal
    card_dues: Decimal

    @property
    def assets(self) -> Decimal:

        """Everything owned, at today's values."""

        return self.cash + self.deposits + self.retirement + self.property + self.other_assets + self.investments

    @property
    def owed(self) -> Decimal:

        """Everything owed: loan balances and card dues."""

        return self.loans + self.card_dues

    @property
    def value(self) -> Decimal:

        """Net worth: owned minus owed."""

        return self.assets - self.owed

    @property
    def split(self) -> list[tuple[str, Decimal]]:

        """The owned side by type, largest first, leaving out empty types."""

        parts = [
            ("Property", self.property),
            ("Stocks & funds", self.investments),
            ("EPF, PPF & NPS", self.retirement),
            ("Bank & FDs", self.cash + self.deposits),
            ("Other assets", self.other_assets),
            ]

        return sorted((part for part in parts if part[1] > 0), key=lambda part: part[1], reverse=True)


@dataclass(frozen=True)
class MonthFlow:

    """One month's money in and out, from transactions."""

    month: date
    income: Decimal
    spending: Decimal

    @property
    def saved(self) -> Decimal:

        """What was left that month."""

        return self.income - self.spending


@dataclass(frozen=True)
class MonthSummary:

    """This month's income, spending and what is left, with the transaction history behind the trend when there is one."""

    income: int
    spending: int
    history: list[MonthFlow] = field(default_factory=list)

    @property
    def saved(self) -> int:

        """What is left each month after spending."""

        return self.income - self.spending


@dataclass(frozen=True)
class HealthCheck:

    """One part of the health score: what was measured, how it reads, and the points it earned out of 25."""

    label: str
    value: str
    points: float

    @property
    def tone(self) -> str:

        """Full marks read as up, nothing as down, anything between as a warning."""

        if self.points >= CHECK_POINTS:
            return "up"

        if self.points <= 0:
            return "down"

        return "warn"


@dataclass(frozen=True)
class Health:

    """The health score out of 100 and the four checks behind it."""

    checks: list[HealthCheck]

    @property
    def score(self) -> int:

        """The checks' points added up and rounded."""

        return int(round(sum(check.points for check in self.checks)))

    @property
    def verdict(self) -> str:

        """One word for the score."""

        if self.score >= 80:
            return "Strong"

        if self.score >= 60:
            return "Fair"

        if self.score >= 40:
            return "Weak"

        return "At risk"


@dataclass(frozen=True)
class Event:

    """One dated money event for the timeline."""

    on: date
    label: str
    value: Decimal | None
    state: str
    when: str


def money_or_zero(value: Any) -> Decimal:

    """A row's amount as a Decimal, or zero when it is not set."""

    return Decimal(str(value)) if value is not None else Decimal(0)


def net_worth_from(
    accounts: Sequence[Any],
    deposits: Sequence[Any],
    retirement: Sequence[Any],
    assets: Sequence[Any],
    holdings: Sequence[tuple[Decimal | None, Decimal | None]],
    loans: Sequence[Any],
    cards: Sequence[Any],
    ) -> NetWorth:

    """Add up what the user owns and owes from their saved rows; holdings come as (value today, invested) pairs."""

    return NetWorth(
        cash=sum((money_or_zero(row.balance) for row in accounts), Decimal(0)),
        deposits=sum((money_or_zero(row.principal) for row in deposits), Decimal(0)),
        retirement=sum((money_or_zero(row.balance) for row in retirement), Decimal(0)),
        property=sum((money_or_zero(row.current_value) for row in assets if row.asset_type == PhysicalAssetType.real_estate), Decimal(0)),
        other_assets=sum((money_or_zero(row.current_value) for row in assets if row.asset_type != PhysicalAssetType.real_estate), Decimal(0)),
        investments=sum((money_or_zero(value) for value, _ in holdings), Decimal(0)),
        invested=sum((money_or_zero(invested) for _, invested in holdings), Decimal(0)),
        loans=sum((money_or_zero(row.outstanding) for row in loans), Decimal(0)),
        card_dues=sum((money_or_zero(row.outstanding) for row in cards), Decimal(0)),
        )


def month_start(day: date) -> date:

    """The first of the month this day is in."""

    return day.replace(day=1)


def months_back(
    day: date,
    count: int,
    ) -> date:

    """The first of the month `count` months before this day's month; a negative count goes forward."""

    index = day.year * 12 + (day.month - 1) - count

    return date(index // 12, index % 12 + 1, 1)


def history_from(
    transactions: Sequence[Any],
    today: date,
    ) -> list[MonthFlow]:

    """Each of the last six months' inflow and outflow from transactions, oldest first, or nothing when there are no transactions."""

    if not transactions:
        return []

    months = [months_back(today, back) for back in range(HISTORY_MONTHS - 1, -1, -1)]

    flows: dict[date, list[Decimal]] = {month: [Decimal(0), Decimal(0)] for month in months}

    for row in transactions:

        key = month_start(row.txn_date)

        if key not in flows:
            continue

        flows[key][0 if row.direction == TransactionDirection.inflow else 1] += money_or_zero(row.amount)

    return [MonthFlow(month, income, spending) for month, (income, spending) in flows.items()]


def linear_points(
    ratio: float,
    full_at: float,
    ) -> float:

    """Points out of 25 that grow evenly from zero to full marks at `full_at`."""

    return CHECK_POINTS * max(0.0, min(ratio / full_at, 1.0))


def debt_points(ratio: float) -> float:

    """Points out of 25 for debt against income: full up to 30%, none from 60%, even between."""

    if ratio <= DEBT_RATIO_FULL:
        return CHECK_POINTS

    if ratio >= DEBT_RATIO_ZERO:
        return 0.0

    return CHECK_POINTS * (DEBT_RATIO_ZERO - ratio) / (DEBT_RATIO_ZERO - DEBT_RATIO_FULL)


def health_from(
    income: float,
    spending: float,
    emis: float,
    card_dues: float,
    cash: float,
    life_cover: float,
    ) -> Health:

    """Score the four checks from this month's figures; income must be above zero."""

    months = cash / spending if spending > 0 else EMERGENCY_MONTHS_FULL
    debt_ratio = (emis + card_dues) / income
    savings_rate = (income - spending) / income
    cover_multiple = life_cover / (12 * income)

    return Health([
        HealthCheck("Emergency fund", f"{months:.1f} months of spending", linear_points(months, EMERGENCY_MONTHS_FULL)),
        HealthCheck("Debt to income", f"{debt_ratio * 100:.0f}% of income", debt_points(debt_ratio)),
        HealthCheck("Savings rate", f"{savings_rate * 100:.0f}% of income", linear_points(savings_rate, SAVINGS_RATE_FULL)),
        HealthCheck("Life cover", f"₹{indian_number(life_cover)} · {cover_multiple:.1f}× yearly income", linear_points(cover_multiple, COVER_MULTIPLE_FULL)),
        ])


def day_this_month(
    day_of_month: int,
    today: date,
    ) -> date:

    """This month's date for a day number, or the month's last day when the month is shorter."""

    first_next = months_back(today, -1)
    last = first_next - timedelta(days=1)

    return today.replace(day=min(day_of_month, last.day))


def next_monthly(
    day_of_month: int,
    today: date,
    ) -> date:

    """The nearest date for a monthly event: this month's, unless it is more than a week gone, then next month's."""

    this_month = day_this_month(day_of_month, today)

    if this_month < today - timedelta(days=PAST_DAYS):
        return day_this_month(day_of_month, months_back(today, -1))

    return this_month


def state_for(
    on: date,
    today: date,
    ) -> str:

    """past before today, soon within a week, far after that."""

    if on < today:
        return "past"

    if on <= today + timedelta(days=SOON_DAYS):
        return "soon"

    return "far"


def short_day(on: date) -> str:

    """A date as "5 Nov"."""

    return f"{on.day} {on:%b}"


def in_window(
    on: date,
    today: date,
    ) -> bool:

    """Whether a date is from a week ago to thirty days ahead."""

    return today - timedelta(days=PAST_DAYS) <= on <= today + timedelta(days=AHEAD_DAYS)


def events_from(
    today: date,
    sips: Sequence[tuple[Any, str]],
    loans: Sequence[Any],
    cards: Sequence[Any],
    deposits: Sequence[Any],
    policies: Sequence[Any],
    goals: Sequence[Any],
    ) -> list[Event]:

    """The dated events in the window, soonest first, then the active goals by year, up to ten; sips come as (plan, fund name) pairs."""

    dated: list[Event] = []

    def add(
        on: date,
        label: str,
        value: Decimal | None,
        ) -> None:

        """Keep a dated event when it falls in the window."""

        if in_window(on, today):
            dated.append(Event(on, label, value, state_for(on, today), short_day(on)))

    for plan, name in sips:

        if plan.is_active:
            add(next_monthly(plan.sip_day, today), f"SIP · {name}", money_or_zero(plan.amount))

    for loan in loans:
        add(next_monthly(loan.start_date.day, today), f"EMI · {loan.lender}", money_or_zero(loan.emi))

    for card in cards:

        if card.due_day is not None:
            add(next_monthly(card.due_day, today), f"Card due · {card.bank_name}", money_or_zero(card.outstanding))

    for deposit in deposits:
        add(deposit.maturity_date, f"FD matures · {deposit.bank_name}", money_or_zero(deposit.maturity_amount or deposit.principal))

    for policy in policies:

        if policy.renewal_date is not None:
            add(policy.renewal_date, f"Renewal · {policy.insurer}", money_or_zero(policy.premium))

    dated.sort(key=lambda event: event.on)

    goal_events = [
        Event(date(goal.target_year, 1, 1), f"Goal · {goal.name}", money_or_zero(goal.target_amount), "far", str(goal.target_year))
        for goal in sorted(goals, key=lambda goal: goal.target_year)
        if goal.status == GoalStatus.active
        ]

    return (dated + goal_events)[:MAX_EVENTS]


class OverviewService:

    """Load one user's rows and run the overview maths on them; it never writes."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the session and the shared user record queries."""

        self.session = session
        self.repo = BaseUserRecordRepository(session)

    async def holding_values(self, user_id: int) -> list[tuple[Decimal | None, Decimal | None]]:

        """Each holding's value today, from the latest price when known, with what was put in."""

        holdings = await self.repo.list_for_user(Holding, user_id)
        named = await MarketService(self.session).describe_holdings(holdings)

        pairs = []

        for holding in holdings:

            value = named.get(holding.id, {}).get("value_today")

            pairs.append((Decimal(str(value)) if value is not None else holding.current_value, holding.invested_amount))

        return pairs

    async def net_worth(self, user_id: int) -> NetWorth:

        """Everything the user owns and owes."""

        return net_worth_from(
            await self.repo.list_for_user(BankAccount, user_id),
            await self.repo.list_for_user(FixedDeposit, user_id),
            await self.repo.list_for_user(RetirementAccount, user_id),
            await self.repo.list_for_user(PhysicalAsset, user_id),
            await self.holding_values(user_id),
            await self.repo.list_for_user(Loan, user_id),
            await self.repo.list_for_user(CreditCard, user_id),
            )

    async def cash_flow(
        self,
        user_id: int,
        today: date,
        ) -> MonthlyCashFlow:

        """This month's income, expenses, EMIs and premiums from the saved recurring items."""

        return await AnalysisService(self.session).monthly_cash_flow(user_id, today)

    async def month_summary(
        self,
        user_id: int,
        today: date,
        ) -> MonthSummary:

        """This month's figures, with the transaction history when there is one."""

        flow = await self.cash_flow(user_id, today)

        history = history_from(await self.repo.list_for_user(Transaction, user_id), today)

        return MonthSummary(flow.income, flow.expenses + flow.emis + flow.premiums, history)

    async def health(
        self,
        user_id: int,
        today: date,
        ) -> Health | None:

        """The health score, or None when no monthly income is saved yet."""

        flow = await self.cash_flow(user_id, today)

        if flow.income <= 0:
            return None

        worth = await self.net_worth(user_id)

        cover = sum(
            (money_or_zero(policy.cover_amount) for policy in await self.repo.list_for_user(InsurancePolicy, user_id) if policy.policy_type in LIFE_POLICIES),
            Decimal(0),
            )

        return health_from(
            float(flow.income),
            float(flow.expenses + flow.emis + flow.premiums),
            float(flow.emis),
            float(worth.card_dues),
            float(worth.cash),
            float(cover),
            )

    async def upcoming(
        self,
        user_id: int,
        today: date,
        ) -> list[Event]:

        """What is coming up in the next month, then the goals."""

        holdings = await self.repo.list_for_user(Holding, user_id)
        named = await MarketService(self.session).describe_holdings(holdings)

        sips = [
            (plan, named.get(plan.holding_id, {}).get("name") or "fund")
            for plan in await self.repo.list_for_user(SipPlan, user_id)
            ]

        return events_from(
            today,
            sips,
            await self.repo.list_for_user(Loan, user_id),
            await self.repo.list_for_user(CreditCard, user_id),
            await self.repo.list_for_user(FixedDeposit, user_id),
            await self.repo.list_for_user(InsurancePolicy, user_id),
            await self.repo.list_for_user(Goal, user_id),
            )
