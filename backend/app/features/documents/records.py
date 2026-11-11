"""Finding the user's saved record a row matches, by type and name, and telling an update from no change."""

from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BankAccount,
    CreditCard,
    Expense,
    FamilyMember,
    FixedDeposit,
    Goal,
    Holding,
    IncomeSource,
    InsurancePolicy,
    Loan,
    PhysicalAsset,
    RetirementAccount,
    SipPlan,
    Transaction,
    User,
    )
from app.db.session import Base
from app.features.documents.normalize import header_key


MODELS: dict[str, type[Base]] = {
    "users": User,
    "family_members": FamilyMember,
    "income_sources": IncomeSource,
    "expenses": Expense,
    "transactions": Transaction,
    "holdings": Holding,
    "sip_plans": SipPlan,
    "bank_accounts": BankAccount,
    "fixed_deposits": FixedDeposit,
    "retirement_accounts": RetirementAccount,
    "physical_assets": PhysicalAsset,
    "loans": Loan,
    "credit_cards": CreditCard,
    "insurance_policies": InsurancePolicy,
    "goals": Goal,
    }

MATCH_KEYS: dict[str, tuple[str, ...]] = {
    "family_members": ("relation", "name"),
    "income_sources": ("source_type", "name"),
    "expenses": ("category", "name"),
    "transactions": ("txn_date", "amount", "direction", "description"),
    "bank_accounts": ("account_type", "bank_name"),
    "fixed_deposits": ("deposit_type", "bank_name"),
    "retirement_accounts": ("account_type",),
    "physical_assets": ("asset_type", "name"),
    "loans": ("loan_type",),
    "credit_cards": ("bank_name",),
    "insurance_policies": ("policy_type", "insurer"),
    "goals": ("goal_type", "name"),
    }

LABEL_AMOUNTS = ("amount", "balance", "outstanding", "current_value", "principal", "target_amount", "cover_amount", "units")


def plain(value: Any) -> Any:

    """A saved or parsed value in one comparable form: enums as their value, dates as text, numbers as Decimal, text tidied."""

    if isinstance(value, Enum):
        value = value.value

    if isinstance(value, date):
        value = value.isoformat()

    if isinstance(value, bool) or value is None:
        return value

    if isinstance(value, (int, Decimal)):
        return Decimal(value)

    try:
        return Decimal(str(value))

    except InvalidOperation:
        return header_key(value)


def same(
    first: Any,
    second: Any
    ) -> bool:

    """Whether two values are equal once both are in comparable form."""

    return plain(first) == plain(second)


def column_values(
    record: Base,
    fields: list[str]
    ) -> dict[str, Any]:

    """The saved values of the fields a row would change, as plain JSON, for showing old against new."""

    values = {}

    for name in fields:

        value = getattr(record, name)
        values[name] = value.value if isinstance(value, Enum) else value.isoformat() if isinstance(value, date) else str(value) if value is not None else None

    return values


def comparable_fields(
    table: str,
    data: dict[str, Any]
    ) -> list[str]:

    """The row's fields that are real columns of the table, so helper fields like future_value are not compared."""

    columns = MODELS[table].__table__.columns.keys()

    return [name for name in data if name in columns and name not in ("id", "user_id")]


def changes(
    table: str,
    data: dict[str, Any],
    record: Base
    ) -> dict[str, Any]:

    """Only the fields where the row differs from the saved record, each with its old value."""

    return {name: column_values(record, [name])[name] for name in comparable_fields(table, data) if not same(getattr(record, name), data[name])}


def label(
    table: str,
    record: Base
    ) -> str:

    """A short way to name a saved record in a question, such as 'Home loan, outstanding 2500000.00'."""

    parts = [str(plain(getattr(record, key))) for key in MATCH_KEYS.get(table, ()) if getattr(record, key, None) is not None]

    for name in LABEL_AMOUNTS:

        if hasattr(record, name) and getattr(record, name) is not None:
            parts.append(f"{name.replace('_', ' ')} {getattr(record, name)}")
            break

    return ", ".join(parts) or f"saved record {record.id}"


async def saved_records(
    session: AsyncSession,
    table: str,
    user_id: int
    ) -> list[Base]:

    """Every saved record of one table for the user."""

    model = MODELS[table]

    return list(await session.scalars(select(model).where(model.user_id == user_id).order_by(model.id)))


def by_keys(
    table: str,
    data: dict[str, Any],
    records: list[Base]
    ) -> list[Base] | None:

    """The saved records with the same type and name as the row, or None when the row lacks a key to compare."""

    keys = MATCH_KEYS[table]

    if any(data.get(key) in (None, "") for key in keys):
        return None

    return [record for record in records if all(same(getattr(record, key), data[key]) for key in keys)]
