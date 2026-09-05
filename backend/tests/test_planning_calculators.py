"""Reference and boundary cases for the goal, retirement and debt calculators.

These figures were worked out independently rather than captured from the code. A test that
records whatever the function currently returns passes forever, including after a regression,
which for a module that produces the numbers a person acts on is worse than having no test.

The boundaries chosen are the ones that break planning tools in practice: a zero rate, a
target date that has already passed, a goal already fully funded, a retirement where returns
do not beat inflation, and a debt payment too small to cover its own interest. Each has a
plausible wrong answer - a division by zero, a negative contribution presented as a credit, an
infinite loop - and each is asserted to produce the sane one instead.

``test_the_target_is_inflated_before_anything_is_compared_to_it`` guards the mistake that most
flatters a user: projecting against today's sticker price. It is the single most important
assertion in the goal set.

The debt simulation is checked for termination as well as for correctness. A payment that never
clears the balance must stop and say so, because the alternative is a request that hangs.
"""

from datetime import date
from decimal import Decimal

from app.calculations.debt.v1 import LoanInput, compare_strategies, monthly_emi, total_interest
from app.calculations.goals.v1 import GoalInput, months_between, run_goal_projection
from app.calculations.retirement.v1 import RetirementInput, run_retirement_projection


def test_months_between_counts_whole_months_and_never_goes_negative():

    """A horizon in the past is zero months rather than a negative one that would invert the maths."""

    assert months_between(date(2026, 9, 5), date(2027, 9, 5)) == 12
    assert months_between(date(2026, 9, 20), date(2027, 9, 5)) == 11
    assert months_between(date(2027, 9, 5), date(2026, 9, 5)) == 0


def test_the_target_is_inflated_before_anything_is_compared_to_it():

    """A goal ten years out is compared against its future cost, not against today's price."""

    projection = run_goal_projection(
        GoalInput(
            target_amount=Decimal("1000000"),
            target_date=date(2036, 9, 5),
            as_of=date(2026, 9, 5),
            inflation_percent=Decimal("6"),
        )
    )

    assert projection.months_remaining == 120
    assert projection.target_at_maturity > Decimal("1800000")
    assert projection.target_at_maturity < Decimal("1830000")


def test_a_zero_return_still_projects_contributions():

    """With no growth the corpus is simply the contributions paid in, not a division by zero."""

    projection = run_goal_projection(
        GoalInput(
            target_amount=Decimal("120000"),
            target_date=date(2027, 9, 5),
            as_of=date(2026, 9, 5),
            monthly_contribution=Decimal("10000"),
            expected_return_percent=Decimal("0"),
            inflation_percent=Decimal("0"),
        )
    )

    assert projection.projected_from_contributions == Decimal("120000.00")
    assert projection.on_track is True
    assert projection.required_monthly == Decimal("0.00")


def test_an_already_funded_goal_asks_for_nothing_rather_than_a_negative_amount():

    """Over funding reports zero required contribution instead of a negative one a client might display."""

    projection = run_goal_projection(
        GoalInput(
            target_amount=Decimal("100000"),
            target_date=date(2028, 9, 5),
            as_of=date(2026, 9, 5),
            current_corpus=Decimal("500000"),
        )
    )

    assert projection.on_track is True
    assert projection.shortfall == Decimal("0.00")
    assert projection.required_monthly == Decimal("0.00")
    assert any("already reach" in warning for warning in projection.warnings)


def test_a_past_target_date_stops_compounding_and_warns():

    """A target date that has arrived leaves nothing to grow and says so rather than projecting on."""

    projection = run_goal_projection(
        GoalInput(
            target_amount=Decimal("100000"),
            target_date=date(2026, 1, 1),
            as_of=date(2026, 9, 5),
            current_corpus=Decimal("40000"),
        )
    )

    assert projection.months_remaining == 0
    assert projection.projected_corpus == Decimal("40000.00")
    assert any("target date has arrived" in warning for warning in projection.warnings)


def test_an_unfunded_goal_is_flagged():

    """A goal with no corpus and no contribution is called out rather than quietly projected as zero."""

    projection = run_goal_projection(
        GoalInput(
            target_amount=Decimal("500000"),
            target_date=date(2030, 9, 5),
            as_of=date(2026, 9, 5),
        )
    )

    assert any("nothing is currently funding" in warning for warning in projection.warnings)


def test_retirement_requires_more_than_the_expense_multiplied_by_the_years():

    """The corpus needed accounts for expenses rising through retirement, not just for their count."""

    projection = run_retirement_projection(
        RetirementInput(
            current_age=30,
            retirement_age=60,
            longevity_years=30,
            current_monthly_expense=Decimal("50000"),
        )
    )

    assert projection.years_to_retirement == 30
    assert projection.monthly_expense_at_retirement > Decimal("50000")
    assert projection.corpus_required > projection.monthly_expense_at_retirement * 12 * 20


def test_retirement_warns_when_returns_do_not_beat_inflation():

    """A post retirement return at or below inflation is called out, since the corpus shrinks in real terms."""

    projection = run_retirement_projection(
        RetirementInput(
            current_age=40,
            retirement_age=60,
            current_monthly_expense=Decimal("60000"),
            post_retirement_return_percent=Decimal("5"),
            inflation_percent=Decimal("6"),
        )
    )

    assert any("do not beat inflation" in warning for warning in projection.warnings)


def test_the_affordability_warning_uses_the_required_contribution_not_the_raw_gap():

    """A large shortfall over a long horizon is not called unrealistic when the monthly cost is modest."""

    projection = run_retirement_projection(
        RetirementInput(
            current_age=32,
            retirement_age=60,
            current_corpus=Decimal("1500000"),
            monthly_contribution=Decimal("25000"),
            current_monthly_expense=Decimal("70000"),
        )
    )

    assert projection.shortfall > Decimal("20000000")
    assert projection.required_additional_monthly < Decimal("70000")
    assert projection.warnings == []


def test_reaching_retirement_age_stops_accumulation():

    """Someone already at retirement age accumulates nothing further and is told so."""

    projection = run_retirement_projection(
        RetirementInput(
            current_age=60,
            retirement_age=60,
            current_corpus=Decimal("10000000"),
            current_monthly_expense=Decimal("50000"),
        )
    )

    assert projection.months_to_retirement == 0
    assert projection.corpus_projected == Decimal("10000000.00")
    assert any("retirement age has been reached" in warning for warning in projection.warnings)


def test_emi_matches_the_standard_reducing_balance_formula():

    """A known loan produces the payment a lender's own statement would show."""

    assert monthly_emi(Decimal("1000000"), Decimal("10"), 120) == Decimal("13215.07")
    assert monthly_emi(Decimal("4200000"), Decimal("8.65"), 240) == Decimal("36848.29")


def test_a_zero_rate_loan_is_the_principal_divided_by_the_tenure():

    """An interest free loan does not divide by zero, it simply splits the principal."""

    assert monthly_emi(Decimal("120000"), Decimal("0"), 12) == Decimal("10000.00")
    assert total_interest(Decimal("120000"), Decimal("0"), 12) == Decimal("0.00")


def test_avalanche_never_costs_more_interest_than_snowball():

    """Paying the highest rate first is arithmetically optimal, so it cannot lose on interest."""

    loans = [
        LoanInput(id="card", label="Card", principal_outstanding=Decimal("180000"), annual_rate_percent=Decimal("36"), minimum_payment=Decimal("9000")),
        LoanInput(id="personal", label="Personal", principal_outstanding=Decimal("450000"), annual_rate_percent=Decimal("14"), minimum_payment=Decimal("12000")),
        LoanInput(id="car", label="Car", principal_outstanding=Decimal("300000"), annual_rate_percent=Decimal("9.5"), minimum_payment=Decimal("9400")),
    ]

    comparison = compare_strategies(loans, extra_monthly=Decimal("10000"))

    assert comparison.avalanche.total_interest <= comparison.snowball.total_interest
    assert comparison.interest_saved_by_avalanche >= Decimal("0")
    assert comparison.avalanche.payoff_order[0] == "card"


def test_snowball_clears_the_smallest_balance_first():

    """The ordering rule is actually applied, which is what makes the comparison meaningful."""

    loans = [
        LoanInput(id="big", label="Big", principal_outstanding=Decimal("500000"), annual_rate_percent=Decimal("20"), minimum_payment=Decimal("10000")),
        LoanInput(id="small", label="Small", principal_outstanding=Decimal("40000"), annual_rate_percent=Decimal("11"), minimum_payment=Decimal("2000")),
    ]

    comparison = compare_strategies(loans, extra_monthly=Decimal("5000"))

    assert comparison.snowball.payoff_order[0] == "small"
    assert comparison.avalanche.payoff_order[0] == "big"


def test_a_debt_that_never_clears_terminates_and_says_so():

    """A payment below the accruing interest stops at the ceiling and reports the finding."""

    loans = [
        LoanInput(id="card", label="Card", principal_outstanding=Decimal("500000"), annual_rate_percent=Decimal("42"), minimum_payment=Decimal("100")),
    ]

    comparison = compare_strategies(loans, extra_monthly=Decimal("0"))

    assert comparison.avalanche.cleared is False
    assert any("does not clear" in warning for warning in comparison.warnings)


def test_a_single_loan_makes_both_strategies_identical():

    """With one debt there is no ordering to choose, and the comparison says so instead of implying a difference."""

    loans = [
        LoanInput(id="only", label="Only", principal_outstanding=Decimal("200000"), annual_rate_percent=Decimal("12"), minimum_payment=Decimal("10000")),
    ]

    comparison = compare_strategies(loans, extra_monthly=Decimal("0"))

    assert comparison.interest_saved_by_avalanche == Decimal("0.00")
    assert any("identical" in warning for warning in comparison.warnings)
