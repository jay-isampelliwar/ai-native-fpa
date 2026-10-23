"""The per-turn budget: how many model and tool calls and tokens a turn has used, and which limit, if any, it reached."""

from decimal import Decimal
from typing import TypedDict

from langchain_core.messages import AIMessage

from app.core.config import get_settings


MODEL_CALL_LIMIT = "model_call_limit"
TOOL_CALL_LIMIT = "tool_call_limit"
OUTPUT_TOKEN_LIMIT = "output_token_limit"

MILLION = Decimal(1_000_000)


class Budget(TypedDict):

    """What one turn has used so far, carried in the graph state and kept across an approval pause."""

    model_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    limit: str | None


def new_budget() -> Budget:

    """An unused budget, for the start of a turn."""

    return Budget(model_calls=0, tool_calls=0, input_tokens=0, output_tokens=0, limit=None)


def add_model_call(
    budget: Budget,
    answer: AIMessage | None,
    ) -> Budget:

    """Count one model call and the tokens it reported."""

    usage = (answer.usage_metadata if answer is not None else None) or {}

    return Budget(
        model_calls=budget["model_calls"] + 1,
        tool_calls=budget["tool_calls"],
        input_tokens=budget["input_tokens"] + usage.get("input_tokens", 0),
        output_tokens=budget["output_tokens"] + usage.get("output_tokens", 0),
        limit=budget["limit"],
        )


def add_tool_calls(
    budget: Budget,
    count: int,
    ) -> Budget:

    """Count the tool calls that are about to run."""

    return Budget(**{**budget, "tool_calls": budget["tool_calls"] + count})


def with_limit(
    budget: Budget,
    limit: str,
    ) -> Budget:

    """Mark the limit the turn reached, so the next model call wraps up instead of acting."""

    return Budget(**{**budget, "limit": limit})


def limit_reached(budget: Budget) -> str | None:

    """Return the limit the turn has reached before its next model call, or None while it is within every limit."""

    settings = get_settings()

    if budget["limit"] is not None:
        return budget["limit"]

    if budget["model_calls"] >= settings.MAX_MODEL_CALLS:
        return MODEL_CALL_LIMIT

    if budget["output_tokens"] >= settings.MAX_OUTPUT_TOKENS_PER_TURN:
        return OUTPUT_TOKEN_LIMIT

    return None


def over_tool_limit(
    budget: Budget,
    count: int,
    ) -> bool:

    """Say whether running this many more tool calls would take the turn past its tool call limit."""

    return budget["tool_calls"] + count > get_settings().MAX_TOOL_CALLS


def cost_usd(
    budget: Budget,
    model: str,
    ) -> Decimal | None:

    """What the turn's tokens cost on this model, or None for a model with no price set."""

    prices = get_settings().MODEL_PRICES_USD_PER_MILLION.get(model)

    if prices is None:
        return None

    input_price, output_price = (Decimal(str(price)) for price in prices)

    return (budget["input_tokens"] * input_price + budget["output_tokens"] * output_price) / MILLION
