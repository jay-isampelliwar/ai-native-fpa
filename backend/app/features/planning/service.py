"""Business rules for goals, goal allocations, assumptions and the tax profile."""

from decimal import Decimal

from app.db.enums import GoalAssetTable
from app.db.models import Assumption, BankAccount, FixedDeposit, Goal, GoalAllocation, RetirementAccount, TaxProfile
from app.features.planning.repository import PlanningRepository
from app.features.planning.schemas import AssumptionSet, GoalAllocationCreate, GoalCreate, TaxProfileSet
from app.features.records.exceptions import RecordError, RecordNotFound
from app.features.records.service import BaseRecordService


ALLOCATABLE_ASSETS = {
    GoalAssetTable.bank_accounts: BankAccount,
    GoalAssetTable.fixed_deposits: FixedDeposit,
    GoalAssetTable.retirement_accounts: RetirementAccount,
    }
FULL = Decimal("100")


class PlanningService(BaseRecordService[PlanningRepository]):

    """The steps behind the planning tools for one session."""

    repository_class = PlanningRepository

    async def add_goal(self, user_id: int, goal: GoalCreate) -> Goal:

        """Link the named family member, then add the goal."""

        member_id = await self.family_member_id(user_id, goal.family_member_name)

        fields = goal.model_dump(exclude={"family_member_name"})

        record = await self.repo.add_goal(user_id, {**fields, "family_member_id": member_id})

        await self.mark_provided(user_id, "goals")

        return record

    async def set_assumption(self, user_id: int, assumption: AssumptionSet) -> Assumption:

        """Change the saved rate for this key, or add it when there is none yet."""

        existing = await self.repo.find_assumption(user_id, assumption.key)

        if existing is None:
            record = await self.repo.insert(Assumption, user_id, assumption.model_dump())

        else:
            record = await self.repo.update_for_user(Assumption, existing.id, user_id, {"value": assumption.value})

        return record

    async def set_tax_profile(self, user_id: int, profile: TaxProfileSet) -> TaxProfile:

        """Change the saved profile for this year with the given fields, or add it when there is none yet."""

        fields = profile.model_dump(exclude_none=True)

        existing = await self.repo.find_tax_profile(user_id, profile.financial_year)

        if existing is None:
            record = await self.repo.insert(TaxProfile, user_id, fields)

        else:
            record = await self.repo.update_for_user(TaxProfile, existing.id, user_id, fields)

        await self.mark_provided(user_id, "tax_profile")

        return record

    async def allocate_goal(self, user_id: int, allocation: GoalAllocationCreate) -> GoalAllocation:

        """Set aside a share of one asset for one goal, keeping the asset's total across goals at 100% or less."""

        goal = await self.repo.get_for_user(Goal, allocation.goal_id, user_id)

        if goal is None:
            raise RecordNotFound(f"No goal with id {allocation.goal_id}.")

        asset_model = ALLOCATABLE_ASSETS[allocation.asset_table]

        asset = await self.repo.get_for_user(asset_model, allocation.asset_id, user_id)

        if asset is None:
            raise RecordNotFound(f"No {allocation.asset_table.value} item with id {allocation.asset_id}.")

        elsewhere = await self.repo.allocated_to_other_goals(
            user_id,
            allocation.asset_table,
            allocation.asset_id,
            allocation.goal_id,
            )

        if elsewhere + allocation.allocation_pct > FULL:
            raise RecordError(
                f"{elsewhere}% of this asset is already set aside for other goals, so at most {FULL - elsewhere}% is left."
                )

        existing = await self.repo.find_allocation(
            user_id,
            allocation.goal_id,
            allocation.asset_table,
            allocation.asset_id,
            )

        if existing is None:
            record = await self.repo.insert(GoalAllocation, user_id, allocation.model_dump())

        else:
            record = await self.repo.update_for_user(
                GoalAllocation,
                existing.id,
                user_id,
                {"allocation_pct": allocation.allocation_pct},
                )

        return record
