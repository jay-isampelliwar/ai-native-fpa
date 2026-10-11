"""Checked inputs for goals, goal allocations, assumptions and the tax profile."""

import re
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.db.enums import AssumptionKey, GoalAssetTable, GoalType, TaxRegime
from app.features.records.schemas import Amount, Balance, Name, Rate


FINANCIAL_YEAR = re.compile(r"^(\d{4})-(\d{2})$")
MAX_GOAL_YEARS_AHEAD = 60
SEC_80C_LIMIT = Decimal("150000")
SEC_80D_LIMIT = Decimal("100000")


class GoalCreate(BaseModel):

    """One financial goal to add, optionally for a named family member."""

    goal_type: GoalType
    name: Name
    target_amount: Amount
    target_year: int
    priority: int = Field(default=1, ge=1, le=5)
    inflation_rate: Rate | None = None
    family_member_name: Name | None = None

    @field_validator("target_year")
    @classmethod
    def year_ahead(cls, value: int) -> int:

        """Refuse a target year in the past or too far ahead."""

        this_year = date.today().year

        if not this_year <= value <= this_year + MAX_GOAL_YEARS_AHEAD:
            raise ValueError(f"Target year must be between {this_year} and {this_year + MAX_GOAL_YEARS_AHEAD}")

        return value


class GoalAllocationCreate(BaseModel):

    """The share of one saved asset to set aside for one saved goal."""

    goal_id: int = Field(gt=0)
    asset_table: GoalAssetTable
    asset_id: int = Field(gt=0)
    allocation_pct: Rate = Field(gt=0)

    @field_validator("asset_table")
    @classmethod
    def supported_asset(cls, value: GoalAssetTable) -> GoalAssetTable:

        """Refuse holdings until stocks and mutual funds can be saved."""

        if value == GoalAssetTable.holdings:
            raise ValueError("Holdings cannot be allocated yet. Use bank_accounts, fixed_deposits or retirement_accounts")

        return value


class AssumptionSet(BaseModel):

    """One planning rate to set, as a yearly percentage."""

    key: AssumptionKey
    value: Rate


class TaxProfileSet(BaseModel):

    """The tax regime and deductions for one financial year; deductions left out keep their saved value."""

    financial_year: str
    regime: TaxRegime
    sec_80c_used: Balance | None = Field(default=None, le=SEC_80C_LIMIT)
    sec_80d_used: Balance | None = Field(default=None, le=SEC_80D_LIMIT)
    hra_claimed: Balance | None = None

    @field_validator("financial_year")
    @classmethod
    def indian_financial_year(cls, value: str) -> str:

        """Accept only a year like 2026-27, where the second part is the next year."""

        match = FINANCIAL_YEAR.match(value.strip())

        if match is None or (int(match.group(1)) + 1) % 100 != int(match.group(2)):
            raise ValueError("Financial year must look like 2026-27")

        return match.group(0)
