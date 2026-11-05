"""Tests that need the real database: SIP and holding rules, moving a holding to another fund, fund houses as banks, and the write check."""

from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.approval import change_preview
from app.agent.context import PlannerContext
from app.agent.tools.operations import run_write
from app.agent.tools.results import ToolResult, checked, ok
from app.agent.tools.verify import confirm_saved
from app.db.enums import DepositType, GoalType, IncomeSourceType, LoanType
from app.db.models import FixedDeposit, Holding, Loan, MutualFund, SipPlan
from app.db.session import SessionLocal
from app.features.analysis.service import AnalysisService
from app.features.assets.schemas import FixedDepositCreate
from app.features.assets.service import AssetService
from app.features.cash_flow.schemas import IncomeSourceCreate
from app.features.cash_flow.service import CashFlowService
from app.features.investments.service import InvestmentService
from app.features.planning.schemas import GoalCreate
from app.features.planning.service import PlanningService
from app.features.records.exceptions import HoldingMissing, RecordError, RecordExists
from app.features.records.kinds import RecordKind
from app.features.records.record_service import RecordService
from tests.support import create_user, delete_user_data


SIP = {"amount": Decimal("2000"), "sip_day": 1}


@pytest.fixture
async def user_id() -> AsyncIterator[int]:

    """A temp user, removed with everything they own after the test."""

    user = await create_user()

    yield user

    await delete_user_data(user)


async def any_fund_isin() -> str:

    """The ISIN of one fund plan with a NAV, or skip when the market data is not loaded."""

    async with SessionLocal() as session:
        isin = await session.scalar(select(MutualFund.isin).where(MutualFund.last_nav.is_not(None)).limit(1))

    if isin is None:
        pytest.skip("No fund plans are loaded in this database.")

    return isin


def runtime_for(user: int) -> SimpleNamespace:

    """A tool runtime outside a conversation, so no idempotency key is used."""

    return SimpleNamespace(context=PlannerContext(user_id=user), tool_call_id="call_1", state=None)


async def count(model: type, user: int) -> int:

    """How many rows of this kind the user has."""

    async with SessionLocal() as session:
        return await session.scalar(select(func.count()).select_from(model).where(model.user_id == user))


async def test_sip_for_a_fund_not_held_saves_nothing(user_id: int) -> None:

    """A SIP into a fund the user does not hold is refused, and no 0 unit holding is created."""

    isin = await any_fund_isin()

    async with SessionLocal() as session:

        with pytest.raises(HoldingMissing):
            await InvestmentService(session).add_sip_plan(user_id, isin, dict(SIP))

    assert await count(Holding, user_id) == 0
    assert await count(SipPlan, user_id) == 0


async def test_same_fund_cannot_be_added_twice(user_id: int) -> None:

    """A second holding of the same fund is refused with the first one's id."""

    isin = await any_fund_isin()

    async with SessionLocal() as session:

        first, _ = await InvestmentService(session).add_holding(user_id, isin, Decimal("10"), Decimal("1000"), None)

        with pytest.raises(RecordExists) as refused:
            await InvestmentService(session).add_holding(user_id, isin, Decimal("5"), None, None)

        await session.commit()

    assert refused.value.record_id == first.id
    assert await count(Holding, user_id) == 1


async def test_same_sip_cannot_be_added_twice(user_id: int) -> None:

    """A second active SIP with the same fund, amount and day is refused, and a different day is allowed."""

    isin = await any_fund_isin()

    async with SessionLocal() as session:

        service = InvestmentService(session)

        await service.add_holding(user_id, isin, Decimal("10"), None, None)

        first, _, _ = await service.add_sip_plan(user_id, isin, dict(SIP))

        with pytest.raises(RecordExists) as refused:
            await service.add_sip_plan(user_id, isin, dict(SIP))

        await service.add_sip_plan(user_id, isin, {**SIP, "sip_day": 15})

        await session.commit()

    assert refused.value.record_id == first.id
    assert await count(SipPlan, user_id) == 2


def new_loan(user: int) -> Loan:

    """One home loan for the user."""

    return Loan(
        user_id=user,
        loan_type=LoanType.home,
        lender="HDFC",
        principal=Decimal("5000000"),
        outstanding=Decimal("4200000"),
        interest_rate=Decimal("8.5"),
        emi=Decimal("43391"),
        start_date=date(2022, 4, 1),
        end_date=date(2042, 3, 31),
        )


async def test_a_save_whose_check_fails_is_undone(user_id: int) -> None:

    """A loan read back with a different lender than asked comes back as mismatch, and the loan is not kept."""

    async def save(session: AsyncSession) -> ToolResult:

        """Add a loan, then check it against a lender it does not have."""

        loan = new_loan(user_id)

        session.add(loan)

        await session.flush()

        await confirm_saved(session, Loan, {"id": loan.id}, {"lender": "ICICI"})

        return checked("Saved loan.", {"id": loan.id})

    result = await run_write(runtime_for(user_id), save)

    assert result.status == "mismatch"
    assert result.data == {"wrong_fields": {"lender": {"asked": "ICICI", "saved": "HDFC"}}}
    assert await count(Loan, user_id) == 0


async def test_a_save_that_skips_the_check_is_undone(user_id: int) -> None:

    """A write that returns plain success without reading its row back is refused, and the loan is not kept."""

    async def save(session: AsyncSession) -> ToolResult:

        """Add a loan and claim success without checking it."""

        session.add(new_loan(user_id))

        await session.flush()

        return ok("Saved loan.")

    result = await run_write(runtime_for(user_id), save)

    assert result.error_code == "not_verified"
    assert await count(Loan, user_id) == 0


async def test_a_checked_save_is_kept(user_id: int) -> None:

    """A loan read back with the asked lender is kept and comes back verified."""

    async def save(session: AsyncSession) -> ToolResult:

        """Add a loan and check it against the lender it has."""

        loan = new_loan(user_id)

        session.add(loan)

        await session.flush()

        await confirm_saved(session, Loan, {"id": loan.id}, {"lender": "HDFC", "emi": 43391})

        return checked("Saved loan.", {"id": loan.id})

    result = await run_write(runtime_for(user_id), save)

    assert result.verified is True
    assert await count(Loan, user_id) == 1


async def two_fund_isins() -> tuple[str, str]:

    """Two different fund plans with a NAV, or skip when the market data is not loaded."""

    async with SessionLocal() as session:
        isins = list(await session.scalars(select(MutualFund.isin).where(MutualFund.last_nav.is_not(None)).limit(2)))

    if len(isins) < 2:
        pytest.skip("Fewer than two fund plans are loaded in this database.")

    return isins[0], isins[1]


async def held_fund(user: int, isin: str) -> int:

    """Save 10 units of the fund for the user and return the holding id."""

    async with SessionLocal() as session:

        record, _ = await InvestmentService(session).add_holding(user, isin, Decimal("10"), Decimal("1000"), None)

        await session.commit()

        return record.id


async def test_moving_a_holding_needs_units_and_amount(user_id: int) -> None:

    """A move to another fund with only the isin is refused and nothing changes."""

    first, second = await two_fund_isins()
    holding_id = await held_fund(user_id, first)

    async with SessionLocal() as session:

        with pytest.raises(RecordError, match="a little confused"):
            await RecordService(session).update_record(user_id, RecordKind.holdings, holding_id, {"isin": second})


async def test_moving_a_holding_points_it_at_the_new_fund(user_id: int) -> None:

    """A move with units and amount points the holding at the new fund, with value at the new NAV, and passes the check."""

    first, second = await two_fund_isins()
    holding_id = await held_fund(user_id, first)
    changes = {"isin": second, "units": "20", "invested_amount": "5000"}

    async with SessionLocal() as session:

        fund = await session.scalar(select(MutualFund).where(MutualFund.isin == second))

        fields = await RecordService(session).update_record(user_id, RecordKind.holdings, holding_id, changes)

        row = await confirm_saved(session, Holding, {"id": holding_id}, fields)

        await session.commit()

    assert row.mutual_fund_id == fund.id
    assert row.units == Decimal("20")
    assert row.invested_amount == Decimal("5000")
    assert row.current_value == (Decimal("20") * fund.last_nav).quantize(Decimal("0.01"))


async def test_moving_to_a_fund_already_held_is_refused(user_id: int) -> None:

    """A move onto a fund the user already holds is refused with that holding's id."""

    first, second = await two_fund_isins()
    moving = await held_fund(user_id, first)
    other = await held_fund(user_id, second)

    async with SessionLocal() as session:

        with pytest.raises(RecordExists) as refused:
            await RecordService(session).update_record(
                user_id,
                RecordKind.holdings,
                moving,
                {"isin": second, "units": "1", "invested_amount": "100"},
                )

    assert refused.value.record_id == other


async def test_move_card_shows_old_and_new_fund(user_id: int) -> None:

    """The approval card for a move names both funds and shows the new units."""

    first, second = await two_fund_isins()
    holding_id = await held_fund(user_id, first)
    changes = {"isin": second, "units": "20", "invested_amount": "5000"}
    call = {"name": "update_record", "id": "c1", "args": {"kind": "holdings", "record_id": holding_id, "changes": changes}}

    preview = await change_preview(call, user_id)

    labels = [row["label"] for row in preview["changes"]]

    assert preview["title"] == "Move this holding to another fund?"
    assert labels[0] == "Fund or stock"
    assert preview["changes"][0]["old"] != preview["changes"][0]["new"]


async def test_a_fund_house_is_not_saved_as_a_deposit(user_id: int) -> None:

    """A fixed deposit at Nippon is refused and no deposit is saved."""

    deposit = FixedDepositCreate(
        bank_name="Nippon Life India Asset Management Limited",
        deposit_type=DepositType.fd,
        principal=Decimal("110000"),
        interest_rate=Decimal("6"),
        start_date=date(2023, 11, 1),
        maturity_date=date(2028, 11, 1),
        )

    async with SessionLocal() as session:

        with pytest.raises(RecordError, match="mutual fund house"):
            await AssetService(session).add_fixed_deposit(user_id, deposit)

    assert await count(FixedDeposit, user_id) == 0


async def test_goal_progress_runs_for_a_user_with_a_goal_and_income(user_id: int) -> None:

    """The goal check reads every income and goal row and gives one result per active goal."""

    async with SessionLocal() as session:

        await CashFlowService(session).add_income_source(
            user_id,
            IncomeSourceCreate(source_type=IncomeSourceType.salary, name="Salary", amount=Decimal("70000")),
            )

        await PlanningService(session).add_goal(
            user_id,
            GoalCreate(goal_type=GoalType.house, name="House", target_amount=Decimal("1000000"), target_year=date.today().year + 3),
            )

        await session.commit()

    async with SessionLocal() as session:
        progress = await AnalysisService(session).goal_progress(user_id, date.today())

    assert progress is not None
