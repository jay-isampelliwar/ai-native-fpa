"""Checked inputs for adding the user's stocks, mutual funds and SIPs."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

from app.db.enums import HoldingAssetType
from app.features.records.schemas import Amount, Balance, PastDate, Rate


Units = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4)]
Price = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=4)]
FolioNumber = Annotated[str, Field(min_length=1, max_length=30)]
SipDay = Annotated[int, Field(ge=1, le=28)]


class HoldingCreate(BaseModel):

    """One stock or mutual fund plan the user owns, pointing at exactly one market instrument."""

    asset_type: HoldingAssetType
    stock_id: int | None = Field(default=None, gt=0)
    mutual_fund_id: int | None = Field(default=None, gt=0)
    folio_number: FolioNumber | None = None
    units: Units
    avg_buy_price: Price | None = None
    invested_amount: Balance | None = None
    current_value: Balance | None = None
    as_of_date: PastDate = Field(default_factory=date.today)

    @model_validator(mode="after")
    def one_instrument(self) -> Self:

        """Refuse a holding that points at no instrument, at both, or at the wrong kind for its asset type."""

        if self.asset_type == HoldingAssetType.stock and (self.stock_id is None or self.mutual_fund_id is not None):
            raise ValueError("A stock holding needs a stock and no mutual fund")

        if self.asset_type == HoldingAssetType.mutual_fund and (self.mutual_fund_id is None or self.stock_id is not None):
            raise ValueError("A mutual fund holding needs a mutual fund and no stock")

        return self


class SipPlanCreate(BaseModel):

    """One monthly SIP into a holding, starting today unless the user said when."""

    holding_id: int = Field(gt=0)
    amount: Amount
    sip_day: SipDay
    step_up_rate: Rate | None = None
    start_date: date = Field(default_factory=date.today)
    end_date: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def ends_after_start(self) -> Self:

        """Refuse an end date that is not after the start date."""

        if self.end_date is not None and self.end_date <= self.start_date:
            raise ValueError("End date must be after start date")

        return self
