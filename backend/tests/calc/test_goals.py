"""Tests for goal progress: inflation, free cash and monthly savings shared by priority, in whole rupees."""

from datetime import date

import pytest

from app.calc.goals import GoalInput, plan_goals
from app.calc.growth import future_value, monthly_sip, present_value


TODAY = date(2026, 10, 13)


def goal(
    name: str,
    priority: int,
    target: float,
    year: int,
    allocated: float = 0.0,
    ) -> GoalInput:

    """Build a goal with 6% inflation and 7% return, the defaults for a short goal."""

    return GoalInput(
        name=name,
        priority=priority,
        target_today=target,
        target_year=year,
        inflation_pct=6.0,
        return_pct=7.0,
        allocated_today=allocated,
        )


def test_single_goal_short_of_money() -> None:

    """Grows the target by inflation, uses all free cash, then needs a SIP larger than the surplus."""

    [result] = plan_goals([goal("House", 1, 1000000, 2027)], free_cash=60000, monthly_surplus=49000, today=TODAY)

    target_future = future_value(1000000, 6, 14)
    gap = target_future - future_value(60000, 7, 14)

    assert result.months == 14

    assert result.target_future == pytest.approx(target_future, abs=2)

    assert result.cash_used == pytest.approx(60000, abs=2)

    assert result.monthly_need == pytest.approx(monthly_sip(gap, 7, 14), abs=2)

    assert result.monthly_assigned == pytest.approx(49000, abs=2)

    assert result.shortfall == pytest.approx(result.monthly_need - 49000, abs=2)

    assert not result.on_track


def test_free_cash_is_never_counted_twice() -> None:

    """The first goal takes only the cash it needs, and the second goal gets what is left."""

    small, large = plan_goals(
        [goal("Trip", 1, 50000, 2027), goal("Car", 2, 800000, 2027)],
        free_cash=100000,
        monthly_surplus=0,
        today=TODAY,
        )

    trip_cash = present_value(future_value(50000, 6, 14), 7, 14)

    assert small.cash_used == pytest.approx(trip_cash, abs=2)

    assert small.on_track

    assert large.cash_used == pytest.approx(100000 - trip_cash, abs=2)


def test_surplus_goes_to_higher_priority_first() -> None:

    """Priority 1 is fully funded each month before priority 2 gets anything."""

    first, second = plan_goals(
        [goal("Second", 2, 500000, 2030), goal("First", 1, 500000, 2030)],
        free_cash=0,
        monthly_surplus=15000,
        today=TODAY,
        )

    assert first.name == "First"

    assert first.on_track

    assert second.monthly_assigned == pytest.approx(15000 - first.monthly_need, abs=2)

    assert not second.on_track


def test_goal_already_covered_by_allocation() -> None:

    """A goal whose linked assets already beat the grown target needs nothing more."""

    [result] = plan_goals([goal("Trip", 1, 50000, 2027, allocated=100000)], free_cash=0, monthly_surplus=0, today=TODAY)

    assert result.gap == 0

    assert result.monthly_need == 0

    assert result.on_track
