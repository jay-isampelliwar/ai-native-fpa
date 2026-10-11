"""Checked inputs for adding loans and credit cards."""

from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.db.enums import LoanType
from app.features.records.schemas import Amount, Balance, PastDate, Rate, ShortName


class LoanCreate(BaseModel):

    """One loan to add, with every detail its EMI plan depends on."""

    loan_type: LoanType
    lender: ShortName
    principal: Amount
    outstanding: Balance
    interest_rate: Rate
    emi: Amount
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def consistent_terms(self) -> Self:

        """Refuse an end date not after the start, or an outstanding amount above the original loan."""

        if self.end_date <= self.start_date:
            raise ValueError("End date must be after start date")

        if self.outstanding > self.principal:
            raise ValueError("Outstanding amount cannot be more than the original loan amount")

        return self


class CreditCardCreate(BaseModel):

    """One credit card to add, with the amount owed as of today unless stated."""

    bank_name: ShortName
    credit_limit: Amount | None = None
    outstanding: Balance = Decimal("0")
    due_day: int | None = Field(default=None, ge=1, le=31)
    as_of_date: PastDate = Field(default_factory=date.today)
