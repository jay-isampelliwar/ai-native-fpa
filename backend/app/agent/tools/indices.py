"""The index quote tool: the level and change of Nifty 50, Sensex and Bank Nifty now, shown as a quote card."""

from datetime import datetime
from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage

from app.agent.blocks import index_number, ist_time, quote_block
from app.agent.context import PlannerContext
from app.agent.tools.limits import tool_timeout
from app.agent.tools.results import invalid, ok, retryable, to_message
from app.features.indices.schemas import IndexName, IndexQuote
from app.features.indices.service import IST, is_open, quotes


UNAVAILABLE_TEXT = (
    "The index quote could not be read right now. Tell the user that you could not get the "
    "current level. Do not guess a number."
    )


def quote_data(quote: IndexQuote) -> dict[str, Any]:

    """One quote as plain values for the model: level, change, today's range and previous close."""

    change = quote.value - quote.previous_close

    return {
        "index": quote.name,
        "level": index_number(quote.value),
        "change": f"{'+' if change >= 0 else '-'}{index_number(change)}",
        "change_pct": round(change / quote.previous_close * 100, 2),
        "open": quote.open,
        "high": quote.high,
        "low": quote.low,
        "previous_close": quote.previous_close,
        "as_of": ist_time(quote.as_of),
        }


@tool
async def get_index_quote(
    runtime: ToolRuntime[PlannerContext],
    indices: Annotated[list[IndexName], "One or more of nifty_50, sensex and bank_nifty, in the order the user asked."],
    ) -> ToolMessage:

    """Get the current level, today's change, open, high, low and previous close of Nifty 50, Sensex or Bank Nifty, and show them as a quote card. Read-only. During market hours the level may be a few minutes old."""

    if not indices:
        return to_message(invalid("missing_fields", "Name at least one index.", {"missing": ["indices"]}), runtime.tool_call_id)

    found, failed = await quotes(indices, tool_timeout(runtime.context))

    if not found:
        return to_message(retryable(UNAVAILABLE_TEXT, "quote_unavailable"), runtime.tool_call_id)

    market_open = is_open(found[0], datetime.now(IST))

    data: dict[str, Any] = {
        "market_open": market_open,
        "quotes": [quote_data(quote) for quote in found],
        }

    if failed:
        data["not_available"] = [index.value for index in failed]

    status = "open" if market_open else "closed"

    message = f"Quoted {len(found)} {'index' if len(found) == 1 else 'indices'}. The market is {status}."

    if failed:
        message += " Some could not be read; say so."

    return to_message(ok(message, data, quote_block(found, market_open)), runtime.tool_call_id)
