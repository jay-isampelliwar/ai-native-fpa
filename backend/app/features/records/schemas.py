"""Field types every record schema shares: money, rates, names and dates."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field


def clean_text(value: str) -> str:

    """Drop spaces around the text and refuse text that is only spaces."""

    value = value.strip()

    if not value:
        raise ValueError("Cannot be empty")

    return value


def not_in_future(value: date) -> date:

    """Refuse a date after today."""

    if value > date.today():
        raise ValueError("Cannot be in the future")

    return value


Amount = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
Balance = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Rate = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Name = Annotated[str, Field(max_length=255), AfterValidator(clean_text)]
ShortName = Annotated[str, Field(max_length=100), AfterValidator(clean_text)]
PastDate = Annotated[date, AfterValidator(not_in_future)]
