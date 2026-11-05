"""The planning tools: add goals, link assets to goals, and set planning rates and the tax profile."""

from decimal import Decimal
from typing import Annotated

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage

from app.agent.context import PlannerContext
from app.agent.tools.cash_flow import RUPEES
from app.agent.tools.common import save_record
from app.db.enums import AssumptionKey, GoalAssetTable, GoalType, TaxRegime
from app.features.planning.schemas import AssumptionSet, GoalAllocationCreate, GoalCreate, TaxProfileSet
from app.features.planning.service import PlanningService


@tool
async def add_goal(
    runtime: ToolRuntime[PlannerContext],
    goal_type: Annotated[GoalType | None, "What the goal is for."] = None,
    name: Annotated[str | None, "A short label, such as 'Aarav college' or 'Retirement'."] = None,
    target_amount: Annotated[Decimal | None, f"The amount needed in today's money. {RUPEES}"] = None,
    target_year: Annotated[int | None, "The year the money is needed, such as 2035."] = None,
    priority: Annotated[int | None, "1 for most important up to 5, only if the user said it."] = None,
    inflation_rate: Annotated[Decimal | None, "Yearly inflation in percent for this goal, only if stated."] = None,
    family_member_name: Annotated[str | None, "The saved family member this goal is for, if any."] = None,
    ) -> ToolMessage:

    """Add one financial goal, such as a house, a child's education or retirement. Required: goal type, name, target amount in today's money, target year."""

    return await save_record(
        runtime,
        GoalCreate,
        dict(locals()),
        lambda session, user_id, goal: PlanningService(session).add_goal(user_id, goal),
        "goal",
        )


@tool
async def link_asset_to_goal(
    runtime: ToolRuntime[PlannerContext],
    goal_id: Annotated[int | None, "The goal's id, from list_records with kind goals."] = None,
    asset_table: Annotated[GoalAssetTable | None, "bank_accounts, fixed_deposits or retirement_accounts."] = None,
    asset_id: Annotated[int | None, "The asset's id, from list_records for that kind."] = None,
    allocation_pct: Annotated[Decimal | None, "The percent of the asset to set aside for the goal, above 0 and up to 100."] = None,
    ) -> ToolMessage:

    """Set aside a percent of one saved bank account, deposit or retirement account for one saved goal. Setting it again replaces the old percent. Required: all four. Stocks and funds cannot be linked yet."""

    return await save_record(
        runtime,
        GoalAllocationCreate,
        dict(locals()),
        lambda session, user_id, allocation: PlanningService(session).allocate_goal(user_id, allocation),
        "goal allocation",
        )


@tool
async def set_planning_rate(
    runtime: ToolRuntime[PlannerContext],
    key: Annotated[AssumptionKey | None, "Which planning rate to set."] = None,
    value: Annotated[Decimal | None, "The yearly rate in percent, such as 6 for 6%."] = None,
    ) -> ToolMessage:

    """Set one yearly rate the user chose for planning maths, such as inflation or equity return. Replaces the old value. Required: key, value. Not for the user's own interest rates on loans or deposits."""

    return await save_record(
        runtime,
        AssumptionSet,
        dict(locals()),
        lambda session, user_id, assumption: PlanningService(session).set_assumption(user_id, assumption),
        "assumption",
        )


@tool
async def set_tax_profile(
    runtime: ToolRuntime[PlannerContext],
    financial_year: Annotated[str | None, "The Indian financial year, such as 2026-27."] = None,
    regime: Annotated[TaxRegime | None, "old or new tax regime."] = None,
    sec_80c_used: Annotated[Decimal | None, f"Section 80C deductions used, up to 150000, only if stated. {RUPEES}"] = None,
    sec_80d_used: Annotated[Decimal | None, f"Section 80D deductions used, up to 100000, only if stated. {RUPEES}"] = None,
    hra_claimed: Annotated[Decimal | None, f"HRA exemption claimed, only if stated. {RUPEES}"] = None,
    ) -> ToolMessage:

    """Set the user's income tax regime and deductions for one financial year. Updates the year if already saved. Required: financial year, regime."""

    return await save_record(
        runtime,
        TaxProfileSet,
        dict(locals()),
        lambda session, user_id, profile: PlanningService(session).set_tax_profile(user_id, profile),
        "tax profile",
        )
