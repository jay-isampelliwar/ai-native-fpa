"""Finding what the user wants in a new message: keyword rules first, a small model when unsure, and a safe fallback last."""

import asyncio
import logging
import re
from collections.abc import Sequence
from typing import Literal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.constants import TAG_NOSTREAM
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.llm import llm_service


log = logging.getLogger(__name__)

VIEW_DATA = "VIEW_DATA"
ADD_DATA = "ADD_DATA"
CHANGE_DATA = "CHANGE_DATA"
DELETE_DATA = "DELETE_DATA"
GOAL_CHECK = "GOAL_CHECK"
MISSING_DATA = "MISSING_DATA"
SIMULATION = "SIMULATION"
MARKET_INFO = "MARKET_INFO"
GENERAL_QUESTION = "GENERAL_QUESTION"

ALLOWED_INTENTS = (
    VIEW_DATA,
    ADD_DATA,
    CHANGE_DATA,
    DELETE_DATA,
    GOAL_CHECK,
    MISSING_DATA,
    SIMULATION,
    MARKET_INFO,
    GENERAL_QUESTION,
    )

FALLBACK_INTENTS = [GENERAL_QUESTION]

RULES = (
    (DELETE_DATA, re.compile(r"\b(delete|remove)\b")),
    (CHANGE_DATA, re.compile(r"\b(update|change|edit)\b")),
    (VIEW_DATA, re.compile(r"\b(show|list)\b( me)? my\b")),
    (GOAL_CHECK, re.compile(r"\b(goal progress|on track)\b")),
    (MISSING_DATA, re.compile(r"\bwhat( else)? do you need\b|\bwhat('s| is) missing\b")),
    (SIMULATION, re.compile(r"\bwhat (happens )?if\b|\bcalculate\b")),
    (MARKET_INFO, re.compile(r"\b(price|nav|closing|share price|stock price)\b")),
    )

JOINER = re.compile(r"\b(and|also|then|plus)\b|,\s")

NEGATION = re.compile(r"\b(not|no|never|don'?t|doesn'?t|didn'?t|won'?t)\b|n't\b")

SIMPLE_MAX_WORDS = 12

CONTEXT_MESSAGES = 4

CLASSIFIER_PROMPT = (
    "You sort a user's latest chat message into intents for a personal finance planner for Indian households. "
    "Pick every intent the latest message asks for, in the order it asks. Use the earlier messages only to understand "
    "short replies like 'yes' or 'that one'.\n"
    "- VIEW_DATA: see or ask about details they already saved (loans, goals, income, expenses, accounts, policies).\n"
    "- ADD_DATA: share or save a new detail (a new loan, salary, goal, family member, policy).\n"
    "- CHANGE_DATA: change a detail already saved.\n"
    "- DELETE_DATA: remove a detail already saved.\n"
    "- GOAL_CHECK: whether they are on track for a goal.\n"
    "- MISSING_DATA: what details the planner still needs.\n"
    "- SIMULATION: a what-if or a calculation, like spending, buying or paying off early. "
    "'What if I remove the car loan?' is SIMULATION, not DELETE_DATA.\n"
    "- MARKET_INFO: a question about a stock, ETF or mutual fund itself, such as its price or NAV, what a fund holds, "
    "its sectors, which funds hold a stock, comparing funds, or a list of a fund house's schemes. "
    "'I have 100 units of HDFC Flexi Cap' is ADD_DATA.\n"
    "- GENERAL_QUESTION: anything else, like greetings or general money questions.\n"
    "A negated action is not that action: 'don't delete it' is not DELETE_DATA."
    )


class IntentResult(BaseModel):

    """The intents the classifier found in the latest message, in the order the user asked."""

    intents: list[
        Literal[
            "VIEW_DATA",
            "ADD_DATA",
            "CHANGE_DATA",
            "DELETE_DATA",
            "GOAL_CHECK",
            "MISSING_DATA",
            "SIMULATION",
            "MARKET_INFO",
            "GENERAL_QUESTION",
            ]
        ] = Field(description="Every intent in the latest message, at least one")


def latest_user_text(messages: Sequence[AnyMessage]) -> str:

    """The text of the newest user message, or an empty string when there is none."""

    for message in reversed(messages):

        if isinstance(message, HumanMessage):
            return message.text

    return ""


def match_rules(text: str) -> list[str]:

    """Every intent whose keyword rule matches the message, in rule order."""

    lowered = text.lower()

    return [intent for intent, pattern in RULES if pattern.search(lowered)]


def is_simple(text: str) -> bool:

    """Say whether the message is short, asks one thing and has no negation, so a single rule hit can be trusted."""

    lowered = text.lower()

    if len(lowered.split()) > SIMPLE_MAX_WORDS:
        return False

    if lowered.count("?") > 1:
        return False

    return not JOINER.search(lowered) and not NEGATION.search(lowered)


def clean_intents(intents: Sequence[str]) -> list[str]:

    """Keep only allowed intents, once each and in order, or the fallback when none are left."""

    kept = list(dict.fromkeys(intent for intent in intents if intent in ALLOWED_INTENTS))

    return kept or list(FALLBACK_INTENTS)


async def classify_with_model(messages: Sequence[AnyMessage]) -> tuple[list[str], AIMessage | None]:

    """Ask the intent model for the intents of the newest message, given the last few messages, and return them with its raw answer."""

    settings = get_settings()

    model = (
        llm_service.get_model(settings.INTENT_MODEL)
        .with_structured_output(IntentResult, method="function_calling", include_raw=True)
        .with_config(tags=[TAG_NOSTREAM])
        )

    recent = [message for message in messages if isinstance(message, (HumanMessage, AIMessage)) and message.text]

    result = await asyncio.wait_for(
        model.ainvoke([SystemMessage(CLASSIFIER_PROMPT), *recent[-CONTEXT_MESSAGES:]]),
        timeout=settings.INTENT_TIMEOUT_SECONDS,
        )

    parsed: IntentResult | None = result["parsed"]

    return (parsed.intents if parsed is not None else []), result["raw"]


async def detect_current_intents(messages: Sequence[AnyMessage]) -> tuple[list[str], AIMessage | None]:

    """Find the newest message's intents by rules when it is simple, else by the intent model, and the model's raw answer if it ran."""

    text = latest_user_text(messages)

    hits = match_rules(text)

    if len(hits) == 1 and is_simple(text):
        return hits, None

    try:
        intents, answer = await classify_with_model(messages)

    except Exception:

        log.exception("intent classifier failed, using the fallback")

        return list(FALLBACK_INTENTS), None

    return clean_intents(intents), answer
