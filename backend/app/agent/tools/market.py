"""The market tools: read-only answers about stocks, ETFs and mutual funds, and the user's sector mix."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from pydantic import ValidationError

from app.agent.blocks import Block, compare_block, exposure_block, fund_block, search_block, stock_block
from app.agent.context import PlannerContext
from app.agent.tools.limits import tool_session
from app.agent.tools.results import from_record_error, from_validation_error, invalid, ok, to_message
from app.db.enums import FundCategory, FundSubCategory, MarketCapType, StockSector
from app.features.investments.market import InstrumentKind, MarketService, SearchFilters
from app.features.records.exceptions import RecordError


async def read(
    runtime: ToolRuntime[PlannerContext],
    question: Callable[[MarketService], Awaitable[dict[str, Any]]],
    message: Callable[[dict[str, Any]], str],
    card: Callable[[dict[str, Any]], Block | None],
    ) -> ToolMessage:

    """Answer one read-only market question in its own session and send the result, with its card, back to the model."""

    try:

        async with tool_session(runtime.context) as session:
            data = await question(MarketService(session))

    except ValidationError as exc:
        return to_message(from_validation_error(exc), runtime.tool_call_id)

    except RecordError as exc:
        return to_message(from_record_error(exc), runtime.tool_call_id)

    return to_message(ok(message(data), data, card(data)), runtime.tool_call_id)


def search_message(data: dict[str, Any]) -> str:

    """Say how many stocks and fund schemes a search found."""

    stocks = len(data.get("stocks", []))
    funds = len(data.get("funds", []))

    if not stocks and not funds:
        return "Nothing matched. Try fewer or different words."

    return f"Found {stocks} stocks or ETFs and {funds} fund schemes."


@tool
async def search_stocks_and_funds(
    runtime: ToolRuntime[PlannerContext],
    query: Annotated[
        str | None,
        "Name words, an NSE or BSE symbol, or an ISIN, such as 'parag parikh flexi' or 'RELIANCE'. "
        "Leave it out to list by filters alone, such as every large cap fund.",
        ] = None,
    kind: Annotated[InstrumentKind, "stock, etf, fund or any."] = InstrumentKind.any,
    sector: Annotated[StockSector | None, "Only stocks in this sector."] = None,
    market_cap: Annotated[MarketCapType | None, "Only large, mid or small cap stocks."] = None,
    category: Annotated[FundCategory | None, "Only funds of this kind."] = None,
    sub_category: Annotated[FundSubCategory | None, "Only funds in this SEBI category."] = None,
    amc: Annotated[str | None, "Only funds from this fund house, such as 'HDFC' or 'SBI'."] = None,
    limit: Annotated[int | None, "How many stocks and fund schemes to return, up to 20. Default 8."] = None,
    ) -> ToolMessage:

    """Find stocks, ETFs and mutual funds in the market data by name, symbol or ISIN, or list them by filters such as sub_category large_cap or market_cap small. Read-only. Each fund scheme comes with all its plans (direct or regular, growth or idcw) and their ISINs. Give a query, a filter, or both."""

    filters = SearchFilters(sector, market_cap, category, sub_category, amc)

    words = (query or "").strip()

    if not words and not any((sector, market_cap, category, sub_category, amc)):

        result = invalid(
            "missing_fields",
            "Give a name, symbol or ISIN to search, or at least one filter such as sub_category or market_cap.",
            {"missing": ["query or filter"]},
            )

        return to_message(result, runtime.tool_call_id)

    return await read(runtime, lambda market: market.search(words, kind, filters, limit), search_message, search_block)


@tool
async def get_fund_details(
    runtime: ToolRuntime[PlannerContext],
    isin: Annotated[str, "The ISIN of any plan of the fund, from search_stocks_and_funds."],
    top: Annotated[int | None, "How many top holdings to return, up to 50. Default 10."] = None,
    ) -> ToolMessage:

    """Show one mutual fund from the market data: its plans and NAVs, and from its latest monthly portfolio the top holdings, sector split and asset split. Read-only."""

    def message(data: dict[str, Any]) -> str:

        """Say which fund this is and whether its portfolio is loaded."""

        if data["portfolio_available"]:
            return f"Details for {data['scheme']}, portfolio as on {data['portfolio_date']}."

        return f"Details for {data['scheme']}. Its portfolio is not loaded, so holdings and sectors are not known."

    return await read(runtime, lambda market: market.fund_details(isin, top), message, fund_block)


@tool
async def get_stock_details(
    runtime: ToolRuntime[PlannerContext],
    isin_or_symbol: Annotated[str, "The stock's ISIN or NSE or BSE symbol, such as 'HDFCBANK'."],
    ) -> ToolMessage:

    """Show one stock or ETF from the market data: last closing price, sector, market cap, and the fund schemes that hold the most of it. Read-only."""

    return await read(runtime, lambda market: market.stock_details(isin_or_symbol), lambda data: f"Details for {data['name']}.", stock_block)


@tool
async def compare_funds(
    runtime: ToolRuntime[PlannerContext],
    isins: Annotated[list[str], "2 to 4 fund plan ISINs, from search_stocks_and_funds."],
    ) -> ToolMessage:

    """Compare 2 to 4 mutual funds side by side: category, NAV, sector split, asset split, and how many of their stocks are the same (overlap). Read-only."""

    return await read(runtime, lambda market: market.compare(isins), lambda data: f"Compared {len(data['funds'])} funds.", compare_block)


@tool
async def get_portfolio_exposure(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """Add up only the user's own stocks and funds by asset class and sector, splitting each fund by its latest portfolio. Read-only. Use it for "how much do I have in banks?". It does not include bank balances, deposits or property, so it is not net worth."""

    def message(data: dict[str, Any]) -> str:

        """Say how many holdings were counted, or that there are none with a value."""

        if not data["holdings_counted"]:
            return "No saved stocks or funds with a value, so there is nothing to add up."

        return f"Added up {data['holdings_counted']} holdings worth ₹{data['total_value']}."

    return await read(runtime, lambda market: market.exposure(runtime.context.user_id), message, exposure_block)
