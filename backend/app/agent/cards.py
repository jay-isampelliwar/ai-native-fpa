"""Plain-words pieces for approval cards: an item's name, labels, key facts and values written the way a person reads them."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import Numeric, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import HoldingAssetType
from app.db.models import Holding, MutualFund, SipPlan, Stock
from app.db.models.base import UserOwnedMixin
from app.features.records.kinds import KINDS, RecordKind


NOT_SET = "Not set"
MAX_FACTS = 4

LABELS = {
    "amount": "Amount",
    "account_type": "Account type",
    "asset_type": "Type",
    "avg_buy_price": "Average buy price",
    "balance": "Balance",
    "bank_name": "Bank",
    "category": "Category",
    "cover_amount": "Cover",
    "credit_limit": "Credit limit",
    "current_value": "Worth",
    "date_of_birth": "Date of birth",
    "deposit_type": "Deposit type",
    "description": "Note",
    "due_day": "Bill due day",
    "emi": "EMI",
    "employer_contribution": "Employer pays each month",
    "end_date": "Ends on",
    "financial_year": "Financial year",
    "folio_number": "Folio number",
    "frequency": "How often",
    "goal_type": "Goal type",
    "hra_claimed": "HRA claimed",
    "inflation_rate": "Inflation",
    "insurer": "Insurer",
    "interest_rate": "Interest rate",
    "invested_amount": "Money you put in",
    "is_active": "Running",
    "is_dependent": "Depends on you",
    "is_essential": "Must-pay",
    "is_self_occupied": "You live in it",
    "lender": "Lender",
    "loan_type": "Loan type",
    "maturity_amount": "Paid at maturity",
    "maturity_date": "Matures on",
    "monthly_contribution": "You pay each month",
    "name": "Name",
    "outstanding": "Still to pay",
    "policy_name": "Policy name",
    "policy_type": "Policy type",
    "premium": "Premium",
    "premium_frequency": "Premium paid",
    "principal": "Amount put in",
    "priority": "Priority",
    "purchase_date": "Bought on",
    "purchase_value": "Bought for",
    "regime": "Tax regime",
    "relation": "Relation",
    "renewal_date": "Renews on",
    "sec_80c_used": "80C used",
    "sec_80d_used": "80D used",
    "sip_day": "SIP date",
    "source_type": "Income type",
    "start_date": "Started on",
    "status": "Status",
    "step_up_rate": "Yearly step-up",
    "target_amount": "Target",
    "target_year": "Target year",
    "txn_date": "Date",
    "units": "Units",
    "value": "Rate",
    "yearly_growth_rate": "Yearly growth",
    }

NAME_FIELDS = ("name", "policy_name", "lender", "bank_name", "insurer")

TYPE_FIELDS = (
    "source_type",
    "category",
    "account_type",
    "deposit_type",
    "loan_type",
    "policy_type",
    "goal_type",
    "asset_type",
    "relation",
    "frequency",
    "regime",
    "key",
    "direction",
    )

HIDDEN_FIELDS = {
    "stock_id",
    "mutual_fund_id",
    "holding_id",
    "physical_asset_id",
    "family_member_id",
    "goal_id",
    "asset_id",
    "asset_table",
    }

DAY_FIELDS = {"sip_day", "due_day"}

REMOVE_NOTES = {
    RecordKind.holdings: "This only removes it from Mosaic. Your real investment is not sold.",
    RecordKind.sip_plans: "This only removes it from Mosaic. Your real SIP keeps running.",
    RecordKind.loans: "This only removes it from Mosaic. Nothing changes with your lender.",
    RecordKind.credit_cards: "This only removes it from Mosaic. Nothing changes with your bank.",
    RecordKind.bank_accounts: "This only removes it from Mosaic. Nothing changes at your bank.",
    RecordKind.fixed_deposits: "This only removes it from Mosaic. Nothing changes at your bank.",
    RecordKind.insurance: "This only removes it from Mosaic. Your real policy stays active.",
    }

DEFAULT_REMOVE_NOTE = "This only removes it from Mosaic. You can add it again any time."


@dataclass
class Described:

    """How one saved item reads on a card: what it is called, its labels, a one-line summary and its key facts."""

    name: str
    thing: str
    chips: list[str] = field(default_factory=list)
    summary: str | None = None
    facts: list[dict[str, str]] = field(default_factory=list)


def label_of(name: str) -> str:

    """The plain-words label for a field, or its name with spaces when none is set."""

    return LABELS.get(name, name.replace("_", " ").capitalize())


def humanize(value: str) -> str:

    """An enum value such as "mutual_fund" as "Mutual fund", keeping short codes such as EPF in capitals."""

    if len(value) <= 3:
        return value.upper()

    return value.replace("_", " ").capitalize()


def rupees(value: Decimal, places: int = 0) -> str:

    """A rupee amount with Indian commas, such as ₹1,20,000, dropping paise that are zero."""

    rounded = round(Decimal(value), places)
    negative = rounded < 0
    whole, _, paise = f"{abs(rounded):.{places}f}".partition(".")

    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []

        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]

        if head:
            groups.insert(0, head)

        whole = ",".join([*groups, tail])

    text = f"₹{whole}" if not paise or int(paise) == 0 else f"₹{whole}.{paise}"

    return f"-{text}" if negative else text


def plain_number(value: Decimal) -> str:

    """A number without trailing zeros, such as 551.241."""

    text = format(Decimal(value).normalize(), "f")

    return text


def day_of_month(day: int) -> str:

    """A day number as "5th of every month"."""

    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

    return f"{day}{suffix} of every month"


def show(
    model: type[UserOwnedMixin],
    name: str,
    value: Any,
    ) -> str:

    """One value written for a person: rupees, percent, a short date, Yes or No, or plain words."""

    if value is None:
        return NOT_SET

    if isinstance(value, bool):
        return "Yes" if value else "No"

    if isinstance(value, Enum):
        return humanize(str(value.value))

    if isinstance(value, date):
        return f"{value.day} {value:%b %Y}"

    if name in DAY_FIELDS and isinstance(value, int):
        return day_of_month(value)

    column = model.__table__.columns.get(name)
    kind = column.type if column is not None else None

    if isinstance(kind, Numeric) and isinstance(value, (int, float, Decimal)):

        if kind.scale == 2 and kind.precision == 5:
            return f"{plain_number(Decimal(str(value)))}%"

        if kind.scale == 2:
            return rupees(Decimal(str(value)))

        if kind.precision == 14:
            return rupees(Decimal(str(value)), 2)

        return plain_number(Decimal(str(value)))

    return str(value)


def generic_facts(record: UserOwnedMixin) -> list[dict[str, str]]:

    """Up to four key facts of a saved item: money first, then rates and dates, leaving out ids and the name."""

    model = type(record)
    columns = [column for column in model.__table__.columns if column.name not in {"id", "user_id", "created_at", "updated_at"}]

    def rank(column: Any) -> int:

        """Money first, then rates, then dates, then the rest."""

        kind = column.type

        if isinstance(kind, Numeric) and kind.scale == 2 and kind.precision != 5:
            return 0

        if isinstance(kind, Numeric):
            return 1

        if column.name.endswith("date") or column.name.endswith("_year"):
            return 2

        return 3

    shown = [
        column for column in columns
        if column.name not in HIDDEN_FIELDS
        and column.name not in NAME_FIELDS
        and column.name not in TYPE_FIELDS
        and getattr(record, column.name) is not None
        ]

    shown.sort(key=rank)

    return [{"label": label_of(column.name), "value": show(model, column.name, getattr(record, column.name))} for column in shown[:MAX_FACTS]]


def generic_describe(
    kind: RecordKind,
    record: UserOwnedMixin,
    ) -> Described:

    """Name a saved item by its own name field, or by its type, with its type as a label."""

    label = KINDS[kind].label
    name = next((getattr(record, field_name) for field_name in NAME_FIELDS if getattr(record, field_name, None)), None)
    kind_value = next((getattr(record, field_name) for field_name in TYPE_FIELDS if getattr(record, field_name, None) is not None), None)
    chip = humanize(str(kind_value.value)) if isinstance(kind_value, Enum) else None

    if kind == RecordKind.family:
        return Described(name=name or "this person", thing=name or "this family member", chips=[chip] if chip else [], facts=generic_facts(record))

    if name is None:
        name = f"{chip} {label}" if chip else label

        return Described(name=name, thing=name, chips=[], facts=generic_facts(record))

    return Described(name=name, thing=f"{name} {label}", chips=[chip] if chip else [], facts=generic_facts(record))


async def holding_describe(
    session: AsyncSession,
    holding: Holding,
    ) -> Described:

    """Name a holding by its fund or stock, with plan labels, its units and value today, and its SIP if any."""

    model = Holding
    stock = await session.get(Stock, holding.stock_id) if holding.stock_id else None
    fund = await session.get(MutualFund, holding.mutual_fund_id) if holding.mutual_fund_id else None

    sip_total = await session.scalar(
        select(func.sum(SipPlan.amount)).where(SipPlan.holding_id == holding.id, SipPlan.is_active.is_(True))
        )

    if fund is not None:
        name = fund.base_scheme_name or fund.scheme_name
        chips = ["Mutual fund", f"{humanize(fund.plan_type.value)} plan", humanize(fund.option_type.value)]
        price = fund.last_nav

    elif stock is not None:
        name = stock.company_name
        chips = ["ETF" if stock.is_etf else "Stock", stock.symbol]
        price = stock.last_price

    else:
        name = "this holding"
        chips = []
        price = None

    worth = holding.units * price if price is not None else holding.current_value
    units = plain_number(holding.units)
    word = "units" if holding.asset_type == HoldingAssetType.mutual_fund else "shares"

    summary = f"You hold {units} {word}" + (f", worth about {rupees(worth)} today." if worth is not None else ".")

    facts = [
        {"label": label_of("units"), "value": units},
        {"label": "Worth today", "value": rupees(worth) if worth is not None else NOT_SET},
        {"label": label_of("invested_amount"), "value": show(model, "invested_amount", holding.invested_amount)},
        {"label": "Monthly SIP", "value": rupees(sip_total) if sip_total else "None"},
        ]

    return Described(name=name, thing=name, chips=chips, summary=summary, facts=facts)


async def sip_describe(
    session: AsyncSession,
    plan: SipPlan,
    ) -> Described:

    """Name a SIP by the fund it goes into, with its amount, date and start."""

    holding = await session.get(Holding, plan.holding_id)
    inner = await holding_describe(session, holding) if holding is not None else None
    fund_name = inner.name if inner is not None else "a fund"

    facts = [
        {"label": "Each month", "value": rupees(plan.amount)},
        {"label": label_of("sip_day"), "value": day_of_month(plan.sip_day)},
        {"label": label_of("start_date"), "value": show(SipPlan, "start_date", plan.start_date)},
        {"label": label_of("is_active"), "value": "Yes" if plan.is_active else "No"},
        ]

    return Described(
        name=f"SIP in {fund_name}",
        thing=f"{rupees(plan.amount)} SIP in {fund_name}",
        chips=["SIP", *(inner.chips[1:] if inner else [])],
        facts=facts,
        )


async def describe(
    session: AsyncSession,
    kind: RecordKind,
    record: UserOwnedMixin,
    ) -> Described:

    """How one saved item reads on a card, with real fund and stock names for holdings and SIPs."""

    if kind == RecordKind.holdings:
        return await holding_describe(session, record)

    if kind == RecordKind.sip_plans:
        return await sip_describe(session, record)

    return generic_describe(kind, record)


def change_title(
    kind: RecordKind,
    described: Described,
    ) -> str:

    """The question at the top of a change card, naming the item."""

    if kind == RecordKind.family:
        return f"Change {described.name}'s details?"

    return f"Change your {described.thing}?"


def remove_title(described: Described) -> str:

    """The question at the top of a remove card, naming the item."""

    return f"Remove {described.thing} from your list?"


def remove_note(kind: RecordKind) -> str:

    """The calming line under a remove card that says what removing does not do."""

    return REMOVE_NOTES.get(kind, DEFAULT_REMOVE_NOTE)
