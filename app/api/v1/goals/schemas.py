"""Request and response shapes for goals and the assets earmarked against them.

``GoalRead`` returns funding rather than a stored balance, and it returns ``valued_at_cost``
alongside it. A client showing a funded figure without that flag would be implying a market
valuation the backend never made, and the honest presentation depends on the flag reaching
the interface.

``target_date`` has no upper bound but ``priority`` does. A goal fifty years out is unusual
but legitimate; a priority outside one to five is a client bug, and catching it here is
cheaper than a check constraint violation surfacing as a 500.

``FundingLink`` names the asset by table and id, mirroring how ``goal_fundings`` stores it. The
allowed tables are constrained at the database level too, so a bad value is refused twice - once
with a readable message here, once as a guarantee there.

``inflation_percent`` is settable per goal rather than global. Education inflation in India runs
well above general inflation, and a single figure across every goal would understate exactly the
targets people care most about.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.finance import DepositKind, HoldingKind

FUNDABLE_TABLES = ("holdings", "deposits", "sip_records", "retirement_assets")


class GoalCreate(BaseModel):

    """One savings target, recorded with the inflation rate that applies to this kind of goal."""

    user_id: int
    label: str = Field(min_length=1, max_length=120)
    target_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    target_date: date
    kind: str = Field(default="custom", max_length=40)
    priority: int = Field(default=3, ge=1, le=5)
    inflation_percent: Decimal = Field(default=Decimal("6.000"), ge=0, le=30, max_digits=6, decimal_places=3)


class GoalRead(BaseModel):

    """A goal with its funding valued at read time, flagged as cost rather than market value."""

    id: str
    label: str
    kind: str
    target_amount: Decimal
    target_date: date
    priority: int
    inflation_percent: Decimal
    funded_corpus: Decimal
    monthly_contribution: Decimal
    valued_at_cost: bool
    evidence_ids: list[str]


class FundingLink(BaseModel):

    """Earmarks an existing asset for a goal, optionally only a share of it."""

    user_id: int
    asset_table: str = Field(pattern="^(holdings|deposits|sip_records|retirement_assets)$")
    asset_id: str
    allocation_pct: Decimal = Field(default=Decimal("100.00"), gt=0, le=100, max_digits=5, decimal_places=2)


class DepositCreate(BaseModel):

    """A term or recurring deposit, whose kind decides which amount is required."""

    user_id: int
    kind: DepositKind
    institution: str = Field(min_length=1, max_length=120)
    interest_rate_percent: Decimal = Field(ge=0, le=30, max_digits=6, decimal_places=3)
    opened_on: date
    matures_on: date
    principal: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    monthly_contribution: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    compounding: str = Field(default="quarterly", max_length=20)


class HoldingCreate(BaseModel):

    """A position in one instrument, recorded as units and cost with no current price."""

    user_id: int
    kind: HoldingKind
    instrument_name: str = Field(min_length=1, max_length=160)
    units: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    average_cost: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    as_of: date
    isin: str | None = Field(default=None, max_length=12)
    scheme_code: str | None = Field(default=None, max_length=40)
    folio_id: str | None = Field(default=None, max_length=60)


class RetirementAssetCreate(BaseModel):

    """An accumulation scheme, with the balance as of the date it was last confirmed."""

    user_id: int
    scheme: str = Field(pattern="^(epf|ppf|nps|pension|annuity)$")
    balance: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    as_of: date
    monthly_contribution: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    employer_contribution: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    interest_rate_percent: Decimal | None = Field(default=None, ge=0, le=30, max_digits=6, decimal_places=3)
    account_reference: str | None = Field(default=None, max_length=60)
