"""The investment tools: save a stock or fund the user owns, and a monthly SIP into one."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import PlannerContext
from app.agent.tools.cash_flow import RUPEES
from app.agent.tools.common import given_arguments
from app.agent.tools.operations import run_write
from app.agent.tools.records import record_fields
from app.agent.tools.results import ToolResult, invalid, ok, to_message
from app.features.investments.service import InvestmentService


ISIN_HELP = "The exact ISIN of the stock, ETF or fund plan, from search_instruments. Never guess it."


@tool
async def add_holding(
    runtime: ToolRuntime[PlannerContext],
    isin: Annotated[str | None, ISIN_HELP] = None,
    units: Annotated[Decimal | None, "Units or shares held, only if the user said them."] = None,
    amount: Annotated[Decimal | None, f"Total amount the user invested, only if stated. {RUPEES}"] = None,
    folio_number: Annotated[str | None, "The fund folio number, only if stated."] = None,
    ) -> ToolMessage:

    """Save one stock, ETF or mutual fund plan the user owns. Required: isin, and units or amount. Without units, the app works out units from today's price and asks the user to confirm them."""

    if not isin:
        return to_message(invalid("missing_fields", "Required details missing: isin.", {"missing": ["isin"]}), runtime.tool_call_id)

    if units is None and amount is None:

        result = invalid(
            "missing_fields",
            "Required details missing: units or amount invested.",
            {"missing": ["units or amount"]},
            )

        return to_message(result, runtime.tool_call_id)

    async def save(session: AsyncSession) -> ToolResult:

        """Add the holding in the guard's session."""

        record, instrument = await InvestmentService(session).add_holding(
            runtime.context.user_id,
            isin,
            units,
            amount,
            folio_number,
            )

        return ok(f"Saved {instrument.name}.", {"name": instrument.name, "isin": instrument.isin, **record_fields(record)})

    return to_message(await run_write(runtime, save), runtime.tool_call_id)


@tool
async def add_sip_plan(
    runtime: ToolRuntime[PlannerContext],
    isin: Annotated[str | None, ISIN_HELP] = None,
    amount: Annotated[Decimal | None, f"The monthly SIP amount. {RUPEES}"] = None,
    sip_day: Annotated[int | None, "Day of the month the SIP is paid, 1 to 28."] = None,
    start_date: Annotated[date | None, "When the SIP started, as YYYY-MM-DD, only if stated."] = None,
    step_up_rate: Annotated[Decimal | None, "Yearly step-up in percent, only if stated."] = None,
    end_date: Annotated[date | None, "When the SIP stops, as YYYY-MM-DD, only if stated."] = None,
    ) -> ToolMessage:

    """Save one monthly SIP. Required: isin, amount, SIP day. If the user does not hold that fund yet, a holding with 0 units is added for it first."""

    given = given_arguments(dict(locals()))
    missing = [name.replace("_", " ") for name in ("isin", "amount", "sip_day") if name not in given]

    if missing:
        return to_message(invalid("missing_fields", f"Required details missing: {', '.join(missing)}.", {"missing": missing}), runtime.tool_call_id)

    plan = {name: value for name, value in given.items() if name not in ("isin", "runtime")}

    async def save(session: AsyncSession) -> ToolResult:

        """Add the SIP, and its holding when needed, in the guard's session."""

        record, holding, created = await InvestmentService(session).add_sip_plan(runtime.context.user_id, isin, plan)

        message = "Saved SIP and a new holding with 0 units for it." if created else "Saved SIP."

        return ok(message, {"holding_id": holding.id, "holding_created": created, **record_fields(record)})

    return to_message(await run_write(runtime, save), runtime.tool_call_id)
