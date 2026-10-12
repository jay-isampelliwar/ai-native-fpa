"""Gather a user's goals, cash flow, assets and rates, and run the goal progress maths on them."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.calc.cash_flow import MonthlyCashFlow, monthly_total
from app.calc.goals import GoalInput, GoalResult, plan_goals
from app.calc.growth import months_until_year_end
from app.db.enums import AssumptionKey, GoalAssetTable, GoalStatus, GoalType, PaymentFrequency
from app.db.models import (
    Assumption,
    BankAccount,
    Expense,
    FixedDeposit,
    Goal,
    GoalAllocation,
    IncomeSource,
    InsurancePolicy,
    Loan,
    RetirementAccount,
    )
from app.features.records.base_repository import BaseUserRecordRepository


DEFAULT_RATES = {
    AssumptionKey.inflation: 6.0,
    AssumptionKey.education_inflation: 10.0,
    AssumptionKey.debt_return: 7.0,
    AssumptionKey.equity_return: 12.0,
    }
SHORT_GOAL_MONTHS = 36
FREE_CASH_TABLES = (GoalAssetTable.bank_accounts, GoalAssetTable.fixed_deposits)
FULL = 100.0


@dataclass(frozen=True)
class GoalProgress:

    """The month's cash flow, the free cash shared out, and the result for every active goal."""

    cash_flow: MonthlyCashFlow
    free_cash: float
    goals: list[GoalResult]


def is_current(
    start: date | None,
    end: date | None,
    today: date,
    ) -> bool:

    """True when today falls between an optional start date and an optional end date."""

    return (start is None or start <= today) and (end is None or end >= today)


def return_key(months: int) -> AssumptionKey:

    """Pick the safer debt return for goals under three years away, and equity return for longer ones."""

    return AssumptionKey.debt_return if months < SHORT_GOAL_MONTHS else AssumptionKey.equity_return


class AnalysisService:

    """Read-only analysis for one session; it never writes."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the session and build the shared user record queries on it."""

        self.repo = BaseUserRecordRepository(session)

    async def goal_progress(
        self,
        user_id: int,
        today: date,
        ) -> GoalProgress:

        """Load everything the goal maths needs and return whether each active goal is on track."""

        cash_flow = await self.monthly_cash_flow(user_id, today)
        asset_values = await self.asset_values(user_id)
        allocations = await self.repo.list_for_user(GoalAllocation, user_id)
        rates = await self.rates(user_id)

        allocated_by_goal: dict[int, float] = defaultdict(float)
        allocated_pct_by_asset: dict[tuple[GoalAssetTable, int], float] = defaultdict(float)

        for allocation in allocations:

            key = (allocation.asset_table, allocation.asset_id)
            share = float(allocation.allocation_pct) / FULL

            allocated_by_goal[allocation.goal_id] += asset_values.get(key, 0.0) * share
            allocated_pct_by_asset[key] += float(allocation.allocation_pct)

        free_cash = sum(
            value * max(FULL - allocated_pct_by_asset[key], 0.0) / FULL
            for key, value in asset_values.items()
            if key[0] in FREE_CASH_TABLES
            )

        goals = [goal for goal in await self.repo.list_for_user(Goal, user_id) if goal.status == GoalStatus.active]

        inputs = [self.goal_input(goal, allocated_by_goal[goal.id], rates, today) for goal in goals]

        return GoalProgress(
            cash_flow=cash_flow,
            free_cash=free_cash,
            goals=plan_goals(inputs, free_cash, cash_flow.surplus, today),
            )

    async def monthly_cash_flow(
        self,
        user_id: int,
        today: date,
        ) -> MonthlyCashFlow:

        """Turn current income, expenses, loan EMIs and insurance premiums into one month's figures."""

        incomes = await self.repo.list_for_user(IncomeSource, user_id)
        expenses = await self.repo.list_for_user(Expense, user_id)
        loans = await self.repo.list_for_user(Loan, user_id)
        policies = await self.repo.list_for_user(InsurancePolicy, user_id)

        return MonthlyCashFlow(
            income=monthly_total(
                (item.amount, item.frequency) for item in incomes if is_current(item.start_date, item.end_date, today)
                ),
            expenses=monthly_total(
                (item.amount, item.frequency) for item in expenses if is_current(None, item.end_date, today)
                ),
            emis=monthly_total(
                (item.emi, PaymentFrequency.monthly) for item in loans if is_current(item.start_date, item.end_date, today)
                ),
            premiums=monthly_total(
                (item.premium, item.premium_frequency) for item in policies if is_current(None, item.maturity_date, today)
                ),
            )

    async def asset_values(self, user_id: int) -> dict[tuple[GoalAssetTable, int], float]:

        """Return today's value of every asset a goal can be linked to, keyed by its table and id."""

        values: dict[tuple[GoalAssetTable, int], float] = {}

        for account in await self.repo.list_for_user(BankAccount, user_id):
            values[(GoalAssetTable.bank_accounts, account.id)] = float(account.balance)

        for deposit in await self.repo.list_for_user(FixedDeposit, user_id):
            values[(GoalAssetTable.fixed_deposits, deposit.id)] = float(deposit.principal)

        for account in await self.repo.list_for_user(RetirementAccount, user_id):
            values[(GoalAssetTable.retirement_accounts, account.id)] = float(account.balance)

        return values

    async def rates(self, user_id: int) -> dict[AssumptionKey, float]:

        """Return the user's saved planning rates, filling any gap with the default rate."""

        saved = {item.key: float(item.value) for item in await self.repo.list_for_user(Assumption, user_id)}

        return {**DEFAULT_RATES, **saved}

    def goal_input(
        self,
        goal: Goal,
        allocated_today: float,
        rates: dict[AssumptionKey, float],
        today: date,
        ) -> GoalInput:

        """Build the maths input for one goal, choosing its inflation and return rate."""

        inflation_key = AssumptionKey.education_inflation if goal.goal_type == GoalType.education else AssumptionKey.inflation
        inflation = float(goal.inflation_rate) if goal.inflation_rate is not None else rates[inflation_key]
        months = months_until_year_end(goal.target_year, today)

        return GoalInput(
            name=goal.name,
            priority=goal.priority,
            target_today=float(goal.target_amount),
            target_year=goal.target_year,
            inflation_pct=inflation,
            return_pct=rates[return_key(months)],
            allocated_today=allocated_today,
            )

