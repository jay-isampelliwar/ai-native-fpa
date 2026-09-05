"""Reference and boundary cases for the cash flow calculator, which no other test can substitute for.

Every figure the product shows a user comes from this calculator, so its tests are
written against known answers computed by hand rather than against whatever the code
currently returns. A test that asserts the current output would pass forever, including
after a regression.

The boundaries here are the ones the doc names: zero income, a negative surplus, and
amounts recorded at a frequency other than monthly. Each has been a source of real bugs
in planning tools - a division by zero in a savings rate, a deficit reported as a small
positive number, an annual premium counted twelve times over.

The rounding test matters more than it looks. It asserts that a long list of amounts is
summed at full precision and quantised once, because rounding each element first produces
a total that is off by paisa and a user reconciling against their bank statement will
notice.

``investable_surplus`` is asserted separately from ``free_surplus`` because the two answer
different questions and confusing them is the mistake that would silently overstate how
much a user can commit to a new SIP.
"""

from decimal import Decimal

from app.calculations.cashflow.v1 import CALCULATOR_VERSION, CashflowInput, run_cashflow
from app.calculations.money import MoneyError, percentage, to_money, total
from app.models.finance import Frequency, IncomeRecord


def test_reference_month_matches_hand_computed_figures():

    """A typical salaried month produces the surplus and savings rate worked out by hand."""

    result = run_cashflow(
        CashflowInput(
            income=[Decimal("150000")],
            expenses=[Decimal("55000"), Decimal("12000")],
            emis=[Decimal("32000")],
            sips=[Decimal("10000")],
        )
    )

    assert result.total_income == Decimal("150000.00")
    assert result.committed_outflow == Decimal("99000.00")
    assert result.free_surplus == Decimal("41000.00")
    assert result.investable_surplus == Decimal("51000.00")
    assert result.savings_rate_percent == Decimal("27.33")
    assert result.calculator_version == CALCULATOR_VERSION
    assert result.warnings == []


def test_zero_income_warns_instead_of_dividing_by_zero():

    """A month with no recorded income returns a zero savings rate and says the ratios are unreliable."""

    result = run_cashflow(CashflowInput(expenses=[Decimal("20000")]))

    assert result.savings_rate_percent == Decimal("0.00")
    assert result.free_surplus == Decimal("-20000.00")
    assert any("no income" in warning for warning in result.warnings)


def test_deficit_is_reported_as_negative_and_flagged():

    """Committed outflow above income produces a negative surplus and an explicit deficit warning."""

    result = run_cashflow(
        CashflowInput(
            income=[Decimal("40000")],
            expenses=[Decimal("30000")],
            emis=[Decimal("25000")],
        )
    )

    assert result.free_surplus == Decimal("-15000.00")
    assert any("deficit" in warning for warning in result.warnings)


def test_heavy_emi_load_is_flagged_even_when_the_month_is_positive():

    """EMIs above half of income are warned about although the month still ends in surplus."""

    result = run_cashflow(
        CashflowInput(
            income=[Decimal("100000")],
            expenses=[Decimal("10000")],
            emis=[Decimal("60000")],
        )
    )

    assert result.free_surplus == Decimal("30000.00")
    assert any("half of income" in warning for warning in result.warnings)


def test_investable_surplus_adds_back_the_running_sip():

    """The room available for a larger SIP counts the SIP already running, unlike free surplus."""

    result = run_cashflow(
        CashflowInput(
            income=[Decimal("100000")],
            expenses=[Decimal("40000")],
            sips=[Decimal("15000")],
        )
    )

    assert result.free_surplus == Decimal("45000.00")
    assert result.investable_surplus == Decimal("60000.00")


def test_amounts_are_summed_at_full_precision_and_rounded_once():

    """Three amounts of a third of a rupee total one rupee, not the ninety nine paise per element rounding gives."""

    assert total([Decimal("0.334"), Decimal("0.333"), Decimal("0.333")]) == Decimal("1.00")


def test_house_rounding_is_half_up_not_bankers():

    """Half a paisa rounds up the way an Indian statement does, not to the nearest even digit."""

    assert total([Decimal("0.125")]) == Decimal("0.13")
    assert total([Decimal("0.135")]) == Decimal("0.14")


def test_percentage_of_zero_is_zero_rather_than_an_error():

    """Expressing an amount as a share of nothing returns zero instead of raising."""

    assert percentage(Decimal("500"), Decimal("0")) == Decimal("0.00")


def test_floats_are_refused_at_the_boundary():

    """A float is rejected where it enters rather than silently importing its imprecision."""

    try:
        to_money(1.1)

    except MoneyError:
        return

    raise AssertionError("a float was accepted as money")


def test_annual_amounts_are_normalised_to_one_month():

    """A yearly bonus contributes one twelfth per month rather than its full amount."""

    record = IncomeRecord(
        id="inc_test",
        user_id=1,
        label="Annual bonus",
        amount=Decimal("240000"),
        frequency=Frequency.ANNUAL,
    )

    assert record.monthly_amount == Decimal("20000.00")
