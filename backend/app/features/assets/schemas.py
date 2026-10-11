"""Checked inputs for adding bank accounts, deposits, retirement accounts and physical assets."""

from datetime import date
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.db.enums import BankAccountType, DepositType, PhysicalAssetType, RetirementAccountType
from app.features.records.schemas import Amount, Balance, Name, PastDate, Rate, ShortName


class BankAccountCreate(BaseModel):

    """One bank account to add, with its balance as of today unless stated."""

    bank_name: ShortName
    account_type: BankAccountType
    balance: Balance
    interest_rate: Rate | None = None
    as_of_date: PastDate = Field(default_factory=date.today)


class FixedDepositCreate(BaseModel):

    """One fixed or recurring deposit to add."""

    bank_name: ShortName
    deposit_type: DepositType
    principal: Amount
    interest_rate: Rate
    start_date: date
    maturity_date: date
    maturity_amount: Amount | None = None

    @model_validator(mode="after")
    def matures_after_start(self) -> Self:

        """Refuse a maturity date that is not after the start date."""

        if self.maturity_date <= self.start_date:
            raise ValueError("Maturity date must be after start date")

        return self


class RetirementAccountCreate(BaseModel):

    """One EPF, PPF, NPS or VPF account to add, with its balance as of today unless stated."""

    account_type: RetirementAccountType
    balance: Balance
    monthly_contribution: Balance | None = None
    employer_contribution: Balance | None = None
    interest_rate: Rate | None = None
    maturity_date: date | None = None
    as_of_date: PastDate = Field(default_factory=date.today)


class PhysicalAssetCreate(BaseModel):

    """One house, plot, gold, vehicle or other physical asset to add."""

    asset_type: PhysicalAssetType
    name: Name
    current_value: Amount
    purchase_value: Amount | None = None
    purchase_date: PastDate | None = None
    is_self_occupied: bool = False
