"""The cash flow tools: add regular income, regular expenses and one-off transactions."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage

from app.agent.context import PlannerContext
from app.agent.tools.common import save_record
from app.db.enums import (
    ExpenseCategory,
    IncomeSourceType,
    PaymentFrequency,
    TransactionCategory,
    TransactionDirection,
    )
from app.features.cash_flow.schemas import ExpenseCreate, IncomeSourceCreate, TransactionCreate
from app.features.cash_flow.service import CashFlowService


RUPEES = "In rupees as a plain number, for example 1.5 lakh is 150000."


@tool
async def add_income_source(
    runtime: ToolRuntime[PlannerContext],
    source_type: Annotated[IncomeSourceType | None, "Where the income comes from."] = None,
    name: Annotated[str | None, "A short label the user would recognise, such as 'Infosys salary'."] = None,
    amount: Annotated[Decimal | None, f"The amount received each time. {RUPEES}"] = None,
    frequency: Annotated[PaymentFrequency | None, "How often it is received. Monthly if not said."] = None,
    yearly_growth_rate: Annotated[Decimal | None, "Expected yearly raise in percent, only if the user said it."] = None,
    start_date: Annotated[date | None, "When it started, as YYYY-MM-DD, only if stated."] = None,
    end_date: Annotated[date | None, "When it will stop, as YYYY-MM-DD, only if stated."] = None,
    ) -> ToolMessage:

    """Add one regular income. Required: source type, name, amount."""

    return await save_record(
        runtime,
        IncomeSourceCreate,
        dict(locals()),
        lambda session, user_id, income: CashFlowService(session).add_income_source(user_id, income),
        "income source",
        )


@tool
async def add_expense(
    runtime: ToolRuntime[PlannerContext],
    category: Annotated[ExpenseCategory | None, "What the money is spent on."] = None,
    name: Annotated[str | None, "A short label the user would recognise, such as 'House rent'."] = None,
    amount: Annotated[Decimal | None, f"The amount paid each time. {RUPEES}"] = None,
    frequency: Annotated[PaymentFrequency | None, "How often it is paid. Monthly if not said."] = None,
    is_essential: Annotated[bool | None, "False for wants like dining out, true for needs like rent."] = None,
    end_date: Annotated[date | None, "When it will stop, as YYYY-MM-DD, only if stated."] = None,
    ) -> ToolMessage:

    """Add one regular expense. Required: category, name, amount."""

    return await save_record(
        runtime,
        ExpenseCreate,
        dict(locals()),
        lambda session, user_id, expense: CashFlowService(session).add_expense(user_id, expense),
        "expense",
        )


@tool
async def add_transaction(
    runtime: ToolRuntime[PlannerContext],
    direction: Annotated[TransactionDirection | None, "Inflow if money came in, outflow if it went out."] = None,
    category: Annotated[TransactionCategory | None, "What the one-off amount was for."] = None,
    amount: Annotated[Decimal | None, RUPEES] = None,
    txn_date: Annotated[date | None, "The date it happened, as YYYY-MM-DD."] = None,
    description: Annotated[str | None, "A few words on what it was, only if the user said it."] = None,
    ) -> ToolMessage:

    """Add one one-off amount, such as a bonus, gift or big purchase. Required: direction, category, amount, date."""

    return await save_record(
        runtime,
        TransactionCreate,
        dict(locals()),
        lambda session, user_id, transaction: CashFlowService(session).add_transaction(user_id, transaction),
        "transaction",
        )
