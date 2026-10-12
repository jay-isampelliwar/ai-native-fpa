"""Goal progress maths: grow each target by inflation, then share free cash and monthly savings by priority."""

from dataclasses import dataclass
from datetime import date

from app.calc.growth import future_value, monthly_sip, months_until_year_end, present_value
from app.calc.money import rupees


ON_TRACK_TOLERANCE = 1


@dataclass(frozen=True)
class GoalInput:

    """One goal as the maths needs it: target in today's money, year, rates, and money already set aside."""

    name: str
    priority: int
    target_today: float
    target_year: int
    inflation_pct: float
    return_pct: float
    allocated_today: float


@dataclass(frozen=True)
class GoalResult:

    """Every number behind one goal's verdict, each step rounded to whole rupees so every shown sum adds up exactly."""

    name: str
    priority: int
    target_year: int
    months: int
    inflation_pct: float
    return_pct: float
    target_today: int
    target_future: int
    allocated_today: int
    cash_used: int
    saved_future: int
    gap: int
    monthly_need: int
    monthly_assigned: int
    shortfall: int

    @property
    def on_track(self) -> bool:

        """True when the monthly money handed to this goal covers its monthly need."""

        return self.shortfall < ON_TRACK_TOLERANCE


def plan_goals(
    goals: list[GoalInput],
    free_cash: float,
    monthly_surplus: float,
    today: date,
    ) -> list[GoalResult]:

    """Work out each goal in priority order, giving free cash and then monthly savings to the most important first."""

    cash_left = rupees(max(free_cash, 0.0))
    surplus_left = rupees(max(monthly_surplus, 0.0))
    results = []

    for goal in sorted(goals, key=lambda item: (item.priority, item.target_year, item.name)):

        months = months_until_year_end(goal.target_year, today)
        target_today = rupees(goal.target_today)
        allocated_today = rupees(goal.allocated_today)
        target_future = rupees(future_value(target_today, goal.inflation_pct, months))
        allocated_future = future_value(allocated_today, goal.return_pct, months)
        gap_before_cash = max(target_future - allocated_future, 0.0)

        cash_used = min(cash_left, rupees(present_value(gap_before_cash, goal.return_pct, months)))
        cash_left -= cash_used

        saved_future = rupees(future_value(allocated_today + cash_used, goal.return_pct, months))
        gap = max(target_future - saved_future, 0)

        monthly_need = rupees(monthly_sip(gap, goal.return_pct, months))
        monthly_assigned = min(surplus_left, monthly_need)
        surplus_left -= monthly_assigned

        results.append(
            GoalResult(
                name=goal.name,
                priority=goal.priority,
                target_year=goal.target_year,
                months=months,
                inflation_pct=goal.inflation_pct,
                return_pct=goal.return_pct,
                target_today=target_today,
                target_future=target_future,
                allocated_today=allocated_today,
                cash_used=cash_used,
                saved_future=saved_future,
                gap=gap,
                monthly_need=monthly_need,
                monthly_assigned=monthly_assigned,
                shortfall=monthly_need - monthly_assigned,
                )
            )

    return results
