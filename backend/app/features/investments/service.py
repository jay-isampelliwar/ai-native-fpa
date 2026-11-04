"""Business rules for the user's stocks, mutual funds and SIPs: find the instrument, work out units and values, and save."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from app.db.enums import HoldingAssetType
from app.db.models import Holding, MutualFund, SipPlan, Stock
from app.features.investments.repository import InvestmentRepository
from app.features.investments.schemas import HoldingCreate, SipPlanCreate
from app.features.records.exceptions import RecordError, RecordNotFound
from app.features.records.service import BaseRecordService


COVERAGE_SECTION = "holdings"

PAISE = Decimal("0.01")
FUND_UNIT_STEP = Decimal("0.001")
WHOLE_SHARE = Decimal("1")
PRICE_STEP = Decimal("0.0001")


@dataclass(frozen=True)
class Instrument:

    """One stock, ETF or fund plan the user can hold, with its latest price."""

    asset_type: HoldingAssetType
    record_id: int
    isin: str
    name: str
    price: Decimal | None
    price_date: date | None

    @property
    def price_label(self) -> str:

        """What the price is called for this kind of instrument."""

        return "NAV" if self.asset_type == HoldingAssetType.mutual_fund else "price"


@dataclass(frozen=True)
class UnitEstimate:

    """Units worked out from an amount and the latest price, for the user to confirm."""

    instrument: Instrument
    amount: Decimal
    units: Decimal


def from_stock(stock: Stock) -> Instrument:

    """A stock or ETF as an instrument."""

    return Instrument(HoldingAssetType.stock, stock.id, stock.isin, stock.company_name, stock.last_price, stock.price_date)


def from_fund(fund: MutualFund) -> Instrument:

    """A fund plan as an instrument."""

    return Instrument(HoldingAssetType.mutual_fund, fund.id, fund.isin, fund.scheme_name, fund.last_nav, fund.nav_date)


def units_for(
    instrument: Instrument,
    amount: Decimal,
    ) -> Decimal:

    """Units an amount buys at the latest price: whole shares for a stock, three decimals for a fund."""

    if instrument.price is None or instrument.price <= 0:
        raise RecordError(f"No latest {instrument.price_label} is saved for {instrument.name}, so units cannot be worked out. Ask the user for units.")

    step = FUND_UNIT_STEP if instrument.asset_type == HoldingAssetType.mutual_fund else WHOLE_SHARE

    return (amount / instrument.price).quantize(step, rounding=ROUND_DOWN)


def value_of(
    instrument: Instrument,
    units: Decimal,
    ) -> Decimal | None:

    """Units times the latest price, or None when no price is saved."""

    if instrument.price is None:
        return None

    return (units * instrument.price).quantize(PAISE, rounding=ROUND_HALF_UP)


def buy_price(
    units: Decimal,
    amount: Decimal | None,
    ) -> Decimal | None:

    """The average price paid per unit, or None when the amount or units are unknown."""

    if amount is None or units <= 0:
        return None

    return (amount / units).quantize(PRICE_STEP, rounding=ROUND_HALF_UP)


class InvestmentService(BaseRecordService[InvestmentRepository]):

    """The steps behind the holding and SIP tools for one session."""

    repository_class = InvestmentRepository

    async def instrument(self, isin: str) -> Instrument:

        """Find the stock, ETF or fund plan with this ISIN, or refuse with a message the model can read."""

        isin = isin.strip().upper()

        stock = await self.repo.stock_by_isin(isin)

        if stock is not None:
            return from_stock(stock)

        fund = await self.repo.fund_by_isin(isin)

        if fund is not None:
            return from_fund(fund)

        raise RecordNotFound(f"No stock or fund plan has ISIN {isin}. Use search_instruments to find the right ISIN.")

    async def estimate(
        self,
        isin: str,
        amount: Decimal,
        ) -> UnitEstimate:

        """Work out how many units an amount buys at the latest price."""

        instrument = await self.instrument(isin)

        return UnitEstimate(instrument, amount, units_for(instrument, amount))

    async def add_holding(
        self,
        user_id: int,
        isin: str,
        units: Decimal | None,
        amount: Decimal | None,
        folio_number: str | None,
        ) -> tuple[Holding, Instrument]:

        """Save a holding, working out units from the amount when they are missing, and its value at the latest price."""

        instrument = await self.instrument(isin)

        if units is None:

            if amount is None:
                raise RecordError("Give the units held, or the amount invested so units can be worked out.")

            units = units_for(instrument, amount)

        holding = HoldingCreate(
            asset_type=instrument.asset_type,
            stock_id=instrument.record_id if instrument.asset_type == HoldingAssetType.stock else None,
            mutual_fund_id=instrument.record_id if instrument.asset_type == HoldingAssetType.mutual_fund else None,
            folio_number=folio_number,
            units=units,
            avg_buy_price=buy_price(units, amount),
            invested_amount=amount,
            current_value=value_of(instrument, units),
            )

        record = await self.repo.add_holding(user_id, holding)

        await self.mark_provided(user_id, COVERAGE_SECTION)

        return record, instrument

    async def add_sip_plan(
        self,
        user_id: int,
        isin: str,
        plan: dict,
        ) -> tuple[SipPlan, Holding, bool]:

        """Save a SIP into the user's holding of this instrument, first adding a holding with 0 units when they have none."""

        instrument = await self.instrument(isin)

        stock_id = instrument.record_id if instrument.asset_type == HoldingAssetType.stock else None
        fund_id = instrument.record_id if instrument.asset_type == HoldingAssetType.mutual_fund else None

        holding = await self.repo.holding_for_instrument(user_id, stock_id, fund_id)
        created = holding is None

        if holding is None:
            holding, _ = await self.add_holding(user_id, isin, Decimal(0), None, None)

        record = await self.repo.add_sip_plan(user_id, SipPlanCreate(holding_id=holding.id, **plan))

        await self.mark_provided(user_id, COVERAGE_SECTION)

        return record, holding, created
