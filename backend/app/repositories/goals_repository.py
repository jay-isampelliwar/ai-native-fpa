"""Reads and writes for goals and the assets earmarked against them.

A goal never stores money, so answering "how funded is this goal" means reading the assets
linked to it and valuing them at read time. That is more work than keeping a balance on the
goal row, and it is the only version that cannot go stale: when a deposit matures or a
holding is updated, the goal's funding changes with it and nothing has to be recomputed.

Holdings are valued at cost, not at market. There is no price feed in Phase 2, and inventing
a current value would be exactly the fabrication the whole design forbids. ``valued_at_cost``
on the snapshot says so explicitly, so a skill quoting the figure can say what it is rather
than implying a market valuation.

SIPs linked to a goal contribute to ``monthly_contribution`` rather than to the corpus. An
SIP is an instruction, not an asset - the units it has already bought are in ``holdings`` and
counting both would double the goal's funding.

Deposits contribute their principal for an FD and their contributions to date for an RD, both
excluding interest. That understates funding slightly and deliberately: an accrual model needs
the deposit's compounding convention, and a conservative number is the safer error for a
projection someone will act on.

Every read filters on ``user_id`` and skips archived goals, exactly as the other repositories do.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_scope
from app.models.finance import SipStatus
from app.models.orm.credit import SipRecordRow
from app.models.orm.investments import DepositRow, GoalFundingRow, GoalRow, HoldingRow, RetirementAssetRow


class GoalSnapshot(BaseModel):

    """One goal with the funding actually attached to it, valued at read time rather than stored."""

    model_config = {"arbitrary_types_allowed": True}

    id: str
    label: str
    kind: str
    target_amount: Decimal
    target_date: date
    priority: int
    inflation_percent: Decimal

    funded_corpus: Decimal = Decimal("0")
    monthly_contribution: Decimal = Decimal("0")
    valued_at_cost: bool = True

    evidence_ids: list[str] = Field(default_factory=list)


class GoalsRepository:

    """Creates goals, links funding to them, and reads back what is actually funding each one."""

    async def create_goal(
        self,
        session: AsyncSession,
        user_id: int,
        label: str,
        target_amount: Decimal,
        target_date: date,
        kind: str = "custom",
        priority: int = 3,
        inflation_percent: Decimal = Decimal("6.000"),
        created_by_approval: str | None = None,
        ) -> GoalRow:

        """Record a goal, optionally noting the approval that authorised its creation."""

        row = GoalRow(
            id=f"goal_{uuid4().hex[:12]}",
            user_id=user_id,
            label=label,
            kind=kind,
            target_amount=target_amount,
            target_date=target_date,
            priority=priority,
            inflation_percent=inflation_percent,
            created_by_approval=created_by_approval,
        )

        session.add(row)

        await session.flush()

        return row

    async def link_funding(
        self,
        session: AsyncSession,
        user_id: int,
        goal_id: str,
        asset_table: str,
        asset_id: str,
        allocation_pct: Decimal = Decimal("100.00"),
        ) -> GoalFundingRow | None:

        """Earmark an asset for a goal, refusing when the caller does not own the goal."""

        owns = await session.scalar(
            select(GoalRow.id).where(GoalRow.id == goal_id, GoalRow.user_id == user_id)
        )

        if owns is None:
            return None

        row = GoalFundingRow(
            id=f"fund_{uuid4().hex[:12]}",
            user_id=user_id,
            goal_id=goal_id,
            asset_table=asset_table,
            asset_id=asset_id,
            allocation_pct=allocation_pct,
        )

        session.add(row)

        await session.flush()

        return row

    async def get_snapshot(self, user_id: int, goal_id: str) -> GoalSnapshot | None:

        """Read one goal and value everything linked to it, or report that it does not exist."""

        async with session_scope() as session:
            goal = await session.scalar(
                select(GoalRow).where(
                    GoalRow.id == goal_id,
                    GoalRow.user_id == user_id,
                    GoalRow.archived_at.is_(None),
                )
            )

            if goal is None:
                return None

            return await self._snapshot(session, goal)

    async def list_snapshots(self, user_id: int) -> list[GoalSnapshot]:

        """Read every active goal for one user, each with its funding valued at read time."""

        async with session_scope() as session:
            goals = await session.scalars(
                select(GoalRow)
                .where(GoalRow.user_id == user_id, GoalRow.archived_at.is_(None))
                .order_by(GoalRow.priority, GoalRow.target_date)
            )

            return [await self._snapshot(session, goal) for goal in goals.all()]

    async def _snapshot(self, session: AsyncSession, goal: GoalRow) -> GoalSnapshot:

        """Value every asset linked to one goal and total what it contributes."""

        fundings = (
            await session.scalars(select(GoalFundingRow).where(GoalFundingRow.goal_id == goal.id))
        ).all()

        corpus = Decimal("0")
        monthly = Decimal("0")
        evidence = [goal.id]

        for funding in fundings:

            share = funding.allocation_pct / Decimal("100")

            value, contribution = await self._value_asset(session, funding.asset_table, funding.asset_id)

            corpus += value * share
            monthly += contribution * share

            evidence.append(funding.asset_id)

        linked_sips = (
            await session.scalars(
                select(SipRecordRow).where(
                    SipRecordRow.user_id == goal.user_id,
                    SipRecordRow.linked_goal_id == goal.id,
                    SipRecordRow.status == SipStatus.ACTIVE,
                )
            )
        ).all()

        for sip in linked_sips:

            monthly += sip.amount

            if sip.id not in evidence:
                evidence.append(sip.id)

        return GoalSnapshot(
            id=goal.id,
            label=goal.label,
            kind=goal.kind,
            target_amount=goal.target_amount,
            target_date=goal.target_date,
            priority=goal.priority,
            inflation_percent=goal.inflation_percent,
            funded_corpus=corpus,
            monthly_contribution=monthly,
            evidence_ids=evidence,
        )

    async def _value_asset(
        self,
        session: AsyncSession,
        asset_table: str,
        asset_id: str,
        ) -> tuple[Decimal, Decimal]:

        """Value one linked asset conservatively, returning its corpus and its monthly contribution."""

        if asset_table == "holdings":
            holding = await session.get(HoldingRow, asset_id)

            if holding is None or not holding.active:
                return Decimal("0"), Decimal("0")

            return holding.units * holding.average_cost, Decimal("0")

        if asset_table == "deposits":
            deposit = await session.get(DepositRow, asset_id)

            if deposit is None or not deposit.active:
                return Decimal("0"), Decimal("0")

            return deposit.principal or Decimal("0"), deposit.monthly_contribution or Decimal("0")

        if asset_table == "retirement_assets":
            asset = await session.get(RetirementAssetRow, asset_id)

            if asset is None or not asset.active:
                return Decimal("0"), Decimal("0")

            return asset.balance, asset.monthly_contribution

        if asset_table == "sip_records":
            sip = await session.get(SipRecordRow, asset_id)

            if sip is None or sip.status != SipStatus.ACTIVE:
                return Decimal("0"), Decimal("0")

            return Decimal("0"), sip.amount

        return Decimal("0"), Decimal("0")

    async def update_goal(
        self,
        session: AsyncSession,
        user_id: int,
        goal_id: str,
        changes: dict,
        ) -> bool:

        """Apply changes to one goal this user owns, reporting whether anything matched."""

        if not changes:
            return False

        result = await session.execute(
            update(GoalRow)
            .where(GoalRow.id == goal_id, GoalRow.user_id == user_id, GoalRow.archived_at.is_(None))
            .values(**changes)
        )

        return result.rowcount > 0

    async def archive_goal(
        self,
        session: AsyncSession,
        user_id: int,
        goal_id: str,
        ) -> bool:

        """Retire a goal from every future projection while leaving it readable as history."""

        return await self.update_goal(session, user_id, goal_id, {"archived_at": datetime.now(UTC)})


goals_repository = GoalsRepository()
