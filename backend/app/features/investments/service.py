"""Business rules for the user's stocks, mutual funds and SIPs: find the instrument, work out units and values, and save."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from typing import Any

from app.db.enums import HoldingAssetType
from app.db.models import Holding, MutualFund, SipPlan, Stock
from app.features.investments.repository import InvestmentRepository
from app.features.investments.schemas import HoldingCreate, SipPlanCreate
from app.features.records.exceptions import HoldingMissing, RecordError, RecordExists, RecordNotFound
from app.features.records.service import BaseRecordService


COVERAGE_SECTION = "holdings"
HOLDING_LABEL = "holding of this stock or fund"
HOLDING_HINT = "Change its units or amounts with update_record instead of adding it again."
SIP_HINT = "Do not add it again."
MOVE_NEEDS = ("units", "invested_amount")
MOVE_TEXT = (
    "Moving this holding to another stock or fund needs its units and the amount invested in it. "
    "Tell the user you are a little confused, ask for both, then call update_record again with isin, units and invested_amount."
    )

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


def units_after(
    instrument: Instrument,
    units: Decimal,
    invested: Decimal | None,
    changes: dict[str, Any],
    ) -> Decimal | None:

    """The units a holding has after a money change: from the new current value, or the old units plus what the extra money buys at the latest price; None when units need not change."""

    if changes.get("current_value") is not None:
        return units_for(instrument, Decimal(str(changes["current_value"])))

    if changes.get("invested_amount") is None or invested is None:
        return None

    extra = Decimal(str(changes["invested_amount"])) - Decimal(invested)

    if extra == 0:
        return None

    step = FUND_UNIT_STEP if instrument.asset_type == HoldingAssetType.mutual_fund else WHOLE_SHARE

    if instrument.price is None or instrument.price <= 0:
        raise RecordError(f"No latest {instrument.price_label} is saved for {instrument.name}, so the units for this change cannot be worked out. Ask the user for units.")

    after = (units + extra / instrument.price).quantize(step, rounding=ROUND_DOWN)

    if after <= 0:
        raise RecordError(f"That would leave no units of {instrument.name}. To remove it, call delete_record instead.")

    return after


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

        raise RecordNotFound(f"No stock or fund plan has ISIN {isin}. Use search_stocks_and_funds to find the right ISIN.")

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

        """Save a new holding, refusing one the user already has, working out units from the amount when they are missing."""

        instrument = await self.instrument(isin)

        existing = await self.held(user_id, instrument)

        if existing is not None:
            raise RecordExists(HOLDING_LABEL, existing.id, HOLDING_HINT)

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

    async def held(
        self,
        user_id: int,
        instrument: Instrument,
        ) -> Holding | None:

        """Return the user's holding of this stock or fund plan, or None."""

        stock_id = instrument.record_id if instrument.asset_type == HoldingAssetType.stock else None
        fund_id = instrument.record_id if instrument.asset_type == HoldingAssetType.mutual_fund else None

        return await self.repo.holding_for_instrument(user_id, stock_id, fund_id)

    async def instrument_of(self, holding: Holding) -> Instrument:

        """The stock or fund plan a saved holding points at."""

        if holding.mutual_fund_id is not None:

            fund = await self.repo.fund_by_id(holding.mutual_fund_id)

            if fund is not None:
                return from_fund(fund)

        if holding.stock_id is not None:

            stock = await self.repo.stock_by_id(holding.stock_id)

            if stock is not None:
                return from_stock(stock)

        raise RecordNotFound("This holding's stock or fund is no longer in the market data.")

    async def amount_changes(
        self,
        holding: Holding,
        changes: dict[str, Any],
        ) -> dict[str, Any]:

        """When the money in a holding changes but its units do not, work the units out at the latest price, so value and amount never disagree."""

        if "units" in changes or "isin" in changes:
            return changes

        if changes.get("invested_amount") is None and changes.get("current_value") is None:
            return changes

        instrument = await self.instrument_of(holding)

        units = units_after(instrument, Decimal(holding.units), holding.invested_amount, changes)

        if units is None:
            return changes

        amount = changes.get("invested_amount", holding.invested_amount)

        return {
            **changes,
            "units": units,
            "current_value": value_of(instrument, units),
            "avg_buy_price": buy_price(units, Decimal(str(amount))) if amount is not None else None,
            "as_of_date": date.today(),
            }

    async def move_changes(
        self,
        user_id: int,
        holding: Holding,
        changes: dict[str, Any],
        ) -> dict[str, Any]:

        """Turn an isin in a holding's changes into the columns for the new instrument, needing units and amount, with value at its price."""

        rest = {name: value for name, value in changes.items() if name != "isin"}

        instrument = await self.instrument(str(changes["isin"]))

        columns = {
            "asset_type": instrument.asset_type,
            "stock_id": instrument.record_id if instrument.asset_type == HoldingAssetType.stock else None,
            "mutual_fund_id": instrument.record_id if instrument.asset_type == HoldingAssetType.mutual_fund else None,
            }

        if all(getattr(holding, name) == value for name, value in columns.items()):
            return rest

        missing = [name for name in MOVE_NEEDS if rest.get(name) is None]

        if missing:
            raise RecordError(MOVE_TEXT)

        other = await self.held(user_id, instrument)

        if other is not None and other.id != holding.id:
            raise RecordExists(HOLDING_LABEL, other.id, "Change that one instead, or remove this one.")

        units = Decimal(str(rest["units"]))
        amount = Decimal(str(rest["invested_amount"]))

        return {
            **rest,
            **columns,
            "units": units,
            "invested_amount": amount,
            "avg_buy_price": buy_price(units, amount),
            "current_value": value_of(instrument, units),
            "as_of_date": date.today(),
            }

    async def add_sip_plan(
        self,
        user_id: int,
        isin: str,
        plan: dict,
        ) -> tuple[SipPlan, Holding, Instrument]:

        """Save a SIP into the user's holding of this instrument, refusing when they do not hold it or have the same SIP."""

        instrument = await self.instrument(isin)

        holding = await self.held(user_id, instrument)

        if holding is None:
            raise HoldingMissing(instrument.name)

        sip = SipPlanCreate(holding_id=holding.id, **plan)

        same = await self.repo.active_sip(user_id, holding.id, sip.amount, sip.sip_day)

        if same is not None:
            raise RecordExists("SIP", same.id, SIP_HINT)

        record = await self.repo.add_sip_plan(user_id, sip)

        await self.mark_provided(user_id, COVERAGE_SECTION)

        return record, holding, instrument
