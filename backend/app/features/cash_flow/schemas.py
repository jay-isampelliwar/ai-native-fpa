"""Checked inputs for adding income sources, expenses and transactions."""

from datetime import date
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.db.enums import (
    ExpenseCategory,
    IncomeSourceType,
    PaymentFrequency,
    TransactionCategory,
    TransactionDirection,
    )
from app.features.records.schemas import Amount, Name, Rate


class IncomeSourceCreate(BaseModel):

    """One regular income to add."""

    source_type: IncomeSourceType
    name: Name
    amount: Amount
    frequency: PaymentFrequency = PaymentFrequency.monthly
    yearly_growth_rate: Rate | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def end_after_start(self) -> Self:

        """Refuse an end date that is not after the start date."""

        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError("End date must be after start date")

        return self


class ExpenseCreate(BaseModel):

    """One regular expense to add."""

    category: ExpenseCategory
    name: Name
    amount: Amount
    frequency: PaymentFrequency = PaymentFrequency.monthly
    is_essential: bool = True
    end_date: date | None = None


class TransactionCreate(BaseModel):

    """One one-off amount to add."""

    direction: TransactionDirection
    category: TransactionCategory
    amount: Amount
    txn_date: date
    description: str | None = Field(default=None, max_length=1000)
