"""Database reads and writes for goals, goal allocations, assumptions and the tax profile."""

from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select

from app.db.enums import AssumptionKey, GoalAssetTable
from app.db.models import Assumption, Goal, GoalAllocation, TaxProfile
from app.features.records.base_repository import BaseUserRecordRepository


class PlanningRepository(BaseUserRecordRepository):

    """Planning queries on top of the shared user record queries."""

    async def add_goal(self, user_id: int, fields: dict[str, Any]) -> Goal:

        """Insert a goal for the user."""

        return await self.insert(Goal, user_id, fields)

    async def find_assumption(self, user_id: int, key: AssumptionKey) -> Assumption | None:

        """Return the user's assumption for this key."""

        return await self.find_match(Assumption, user_id, {"key": key})

    async def find_tax_profile(self, user_id: int, financial_year: str) -> TaxProfile | None:

        """Return the user's tax profile for this financial year."""

        return await self.find_match(TaxProfile, user_id, {"financial_year": financial_year})

    async def find_allocation(
        self,
        user_id: int,
        goal_id: int,
        asset_table: GoalAssetTable,
        asset_id: int,
        ) -> GoalAllocation | None:

        """Return the user's allocation of this asset to this goal."""

        return await self.find_match(
            GoalAllocation,
            user_id,
            {"goal_id": goal_id, "asset_table": asset_table, "asset_id": asset_id},
            )

    async def allocated_to_other_goals(
        self,
        user_id: int,
        asset_table: GoalAssetTable,
        asset_id: int,
        goal_id: int,
        ) -> Decimal:

        """Return the percent of this asset already set aside for every goal except this one."""

        query = select(func.coalesce(func.sum(GoalAllocation.allocation_pct), 0)).where(
            GoalAllocation.user_id == user_id,
            GoalAllocation.asset_table == asset_table,
            GoalAllocation.asset_id == asset_id,
            GoalAllocation.goal_id != goal_id,
            )

        return Decimal(await self.session.scalar(query))

    async def delete_allocations_for_goal(self, user_id: int, goal_id: int) -> None:

        """Remove every allocation that points at this goal."""

        await self.session.execute(
            delete(GoalAllocation).where(GoalAllocation.user_id == user_id, GoalAllocation.goal_id == goal_id)
            )

    async def delete_allocations_for_asset(self, user_id: int, asset_table: GoalAssetTable, asset_id: int) -> None:

        """Remove every allocation that points at this asset."""

        await self.session.execute(
            delete(GoalAllocation).where(
                GoalAllocation.user_id == user_id,
                GoalAllocation.asset_table == asset_table,
                GoalAllocation.asset_id == asset_id,
                )
            )
