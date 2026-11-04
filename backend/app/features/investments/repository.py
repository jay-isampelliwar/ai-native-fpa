"""Database reads and writes for the user's holdings and SIPs, and the instrument lookups they need."""

from sqlalchemy import select

from app.db.models import Holding, MutualFund, SipPlan, Stock
from app.features.investments.schemas import HoldingCreate, SipPlanCreate
from app.features.records.base_repository import BaseUserRecordRepository


class InvestmentRepository(BaseUserRecordRepository):

    """Holding and SIP queries on top of the shared user record queries."""

    async def stock_by_isin(self, isin: str) -> Stock | None:

        """Return the listed stock or ETF with this ISIN, or None."""

        return await self.session.scalar(select(Stock).where(Stock.isin == isin))

    async def fund_by_isin(self, isin: str) -> MutualFund | None:

        """Return the mutual fund plan with this ISIN, or None."""

        return await self.session.scalar(select(MutualFund).where(MutualFund.isin == isin))

    async def holding_for_instrument(
        self,
        user_id: int,
        stock_id: int | None,
        mutual_fund_id: int | None,
        ) -> Holding | None:

        """Return the user's first holding of this stock or fund plan, or None."""

        query = select(Holding).where(Holding.user_id == user_id)

        if stock_id is not None:
            query = query.where(Holding.stock_id == stock_id)

        else:
            query = query.where(Holding.mutual_fund_id == mutual_fund_id)

        return await self.session.scalar(query.order_by(Holding.id).limit(1))

    async def add_holding(self, user_id: int, holding: HoldingCreate) -> Holding:

        """Insert a holding for the user."""

        return await self.insert(Holding, user_id, holding.model_dump())

    async def add_sip_plan(self, user_id: int, plan: SipPlanCreate) -> SipPlan:

        """Insert a SIP plan for the user."""

        return await self.insert(SipPlan, user_id, plan.model_dump())
