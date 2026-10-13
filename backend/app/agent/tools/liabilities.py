"""The liability tools: add loans and credit cards."""

import asyncio
from datetime import date
from decimal import Decimal
from typing import Annotated

from langchain.tools import ToolRuntime, tool

from app.agent.context import PlannerContext
from app.agent.tools.cash_flow import RUPEES
from app.agent.tools.common import save_record
from app.db.enums import LoanType
from app.features.liabilities.schemas import CreditCardCreate, LoanCreate
from app.features.liabilities.service import LiabilityService


@tool
async def add_loan(
    runtime: ToolRuntime[PlannerContext],
    loan_type: Annotated[LoanType | None, "The kind of loan."] = None,
    lender: Annotated[str | None, "The bank or lender's name."] = None,
    principal: Annotated[Decimal | None, f"The original loan amount. {RUPEES}"] = None,
    outstanding: Annotated[Decimal | None, f"The amount still left to repay. {RUPEES}"] = None,
    interest_rate: Annotated[Decimal | None, "Yearly interest in percent."] = None,
    emi: Annotated[Decimal | None, f"The monthly EMI. {RUPEES}"] = None,
    start_date: Annotated[date | None, "When the loan started, as YYYY-MM-DD."] = None,
    end_date: Annotated[date | None, "When the last EMI is due, as YYYY-MM-DD."] = None,
    ) -> str:

    """Add one loan. Required: loan type, lender, principal, outstanding, interest rate, EMI, start date, end date."""

    # TODO(orb-demo): remove this delay once the thinking pill has been checked.
    await asyncio.sleep(5)

    return await save_record(
        runtime,
        LoanCreate,
        dict(locals()),
        lambda session, user_id, loan: LiabilityService(session).add_loan(user_id, loan),
        "loan",
        )


@tool
async def add_credit_card(
    runtime: ToolRuntime[PlannerContext],
    bank_name: Annotated[str | None, "The bank that issued the card."] = None,
    credit_limit: Annotated[Decimal | None, f"The card limit, only if stated. {RUPEES}"] = None,
    outstanding: Annotated[Decimal | None, f"The amount owed on the card now. {RUPEES}"] = None,
    due_day: Annotated[int | None, "The day of the month the bill is due, 1 to 31, only if stated."] = None,
    ) -> str:

    """Add one credit card. Required: bank name."""

    return await save_record(
        runtime,
        CreditCardCreate,
        dict(locals()),
        lambda session, user_id, card: LiabilityService(session).add_credit_card(user_id, card),
        "credit card",
        )
