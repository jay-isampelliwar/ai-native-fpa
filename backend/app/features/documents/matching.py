"""Finding the stock or fund a holding row means: exact ISIN or symbol is certain, anything by name becomes choices."""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MutualFund, Stock
from app.features.investments.market import name_matches


MAX_CHOICES = 5

FUND_SEARCH_LIMIT = 60
STOCK_SEARCH_LIMIT = 20
SPACED_SEARCH_LIMIT = 600

FILLER_WORDS = {
    "fund", "plan", "direct", "regular", "growth", "option", "idcw", "dividend", "payout",
    "reinvestment", "the", "of", "dir", "gr", "reg", "ltd", "limited", "india", "scheme", "-",
    }

SYMBOL_SUFFIX = re.compile(r"-[A-Z]{1,2}$")

BRACKETS = re.compile(r"\(.*?\)")

PLAN_BONUS = 0.2
OPTION_BONUS = 0.1


@dataclass
class InstrumentMatch:

    """What the code found for one holding row: a certain instrument, a list of choices, or a reason it found none."""

    instrument: dict[str, Any] | None = None
    choices: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def stock_ref(stock: Stock) -> dict[str, Any]:

    """A stock or ETF as the plain dict a row keeps."""

    return {"kind": "stock", "id": stock.id, "isin": stock.isin, "name": stock.company_name, "symbol": stock.symbol}


def fund_ref(fund: MutualFund) -> dict[str, Any]:

    """A fund plan as the plain dict a row keeps."""

    return {
        "kind": "fund",
        "id": fund.id,
        "isin": fund.isin,
        "name": fund.scheme_name,
        "plan_type": fund.plan_type.value,
        "option_type": fund.option_type.value,
        }


def symbol_forms(name: str) -> list[str]:

    """The name as a symbol, with and without an exchange suffix such as -E, so GOLDBEES-E also tries GOLDBEES."""

    compact = name.strip().upper().replace(" ", "")
    forms = [compact]
    trimmed = SYMBOL_SUFFIX.sub("", compact)

    if trimmed != compact:
        forms.append(trimmed)

    return forms


def search_words(name: str) -> list[str]:

    """The words of a name worth searching on, without plan words like direct or growth."""

    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()

    return [word for word in words if word not in FILLER_WORDS and len(word) > 1]


def plan_wanted(text: str) -> tuple[str | None, str | None]:

    """The plan and option a name or plan hint asks for, such as direct and growth, or None for each when it does not say."""

    lowered = text.lower()
    plan = "direct" if "direct" in lowered else "regular" if re.search(r"\breg(ular)?\b", lowered) else None
    choice = "growth" if "growth" in lowered else "idcw" if re.search(r"idcw|dividend|payout", lowered) else None

    return plan, choice


def score(
    name: str,
    hint: str,
    candidate: dict[str, Any]
    ) -> float:

    """How close a candidate is: name likeness, plus a little when its plan and option fit what the row asks for."""

    likeness = SequenceMatcher(None, search_words(name), search_words(BRACKETS.sub(" ", candidate["name"]))).ratio()
    plan, choice = plan_wanted(f"{name} {hint}")

    if candidate["kind"] == "fund":

        if plan is not None:
            likeness += PLAN_BONUS if candidate["plan_type"] == plan else -PLAN_BONUS

        if choice is not None:
            likeness += OPTION_BONUS if candidate["option_type"] == choice else -OPTION_BONUS

    return likeness


def rank(
    name: str,
    hint: str,
    candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:

    """The closest candidates first, at most MAX_CHOICES of them."""

    ordered = sorted(candidates, key=lambda candidate: score(name, hint, candidate), reverse=True)

    return ordered[:MAX_CHOICES]


async def find_instrument(
    session: AsyncSession,
    data: dict[str, Any]
    ) -> InstrumentMatch:

    """Match a holding row by ISIN, then by exact symbol, and otherwise list the closest stocks and funds by name."""

    isin = data.get("isin")

    if isin:

        stock = await session.scalar(select(Stock).where(Stock.isin == isin))

        if stock is not None:
            return InstrumentMatch(instrument=stock_ref(stock))

        fund = await session.scalar(select(MutualFund).where(MutualFund.isin == isin))

        if fund is not None:
            return InstrumentMatch(instrument=fund_ref(fund))

        return InstrumentMatch(error=f"isin: {isin} is not in the stock or fund list. Check it, or reject this row.")

    name = data.get("security_name")

    if not name:
        return InstrumentMatch(error="security_name: missing. Add the name or ISIN.")

    stocks = list(await session.scalars(select(Stock).where(Stock.symbol.in_(symbol_forms(name)))))

    if len(stocks) == 1:
        return InstrumentMatch(instrument=stock_ref(stocks[0]))

    words = search_words(name)

    if not words:
        return InstrumentMatch(error=f"security_name: '{name}' is too short to search. Add the ISIN.")

    funds = await session.scalars(name_matches(select(MutualFund), MutualFund.scheme_name, words).limit(FUND_SEARCH_LIMIT))
    named_stocks = await session.scalars(name_matches(select(Stock), Stock.company_name, words).limit(STOCK_SEARCH_LIMIT))
    found = [fund_ref(fund) for fund in funds] + [stock_ref(stock) for stock in named_stocks] + await spaced_candidates(session, words)
    unique = {(candidate["kind"], candidate["id"]): candidate for candidate in found}
    candidates = [candidate for candidate in unique.values() if starts_a_word(words[0], candidate["name"])]

    if not candidates:
        return InstrumentMatch(error=f"security_name: no stock or fund in the list matches '{name}'. Add the ISIN.")

    return InstrumentMatch(choices=rank(name, data.get("plan_hint") or "", candidates))


def starts_a_word(
    word: str,
    name: str
    ) -> bool:

    """Whether a search word starts some word of the name, so 'uti' does not match inside 'distribution'."""

    return re.search(rf"\b{re.escape(word)}", name.lower()) is not None


async def spaced_candidates(
    session: AsyncSession,
    words: list[str]
    ) -> list[dict[str, Any]]:

    """Funds whose name has a word starting with the first search word, kept when every word appears once spaces are ignored, so Nifty200 finds Nifty 200."""

    starts = func.lower(MutualFund.scheme_name).op("~")(rf"\m{re.escape(words[0])}")
    funds = await session.scalars(select(MutualFund).where(starts).limit(SPACED_SEARCH_LIMIT))
    kept = []

    for fund in funds:

        compact = fund.scheme_name.lower().replace(" ", "")

        if all(word in compact for word in words):
            kept.append(fund_ref(fund))

    return kept


async def instrument_by_answer(
    session: AsyncSession,
    answer: str
    ) -> dict[str, Any] | None:

    """The stock or fund the user picked, from an answer like fund:123 or stock:45."""

    kind, _, raw_id = answer.partition(":")

    if not raw_id.isdigit():
        return None

    if kind == "fund":
        fund = await session.get(MutualFund, int(raw_id))

        return fund_ref(fund) if fund is not None else None

    if kind == "stock":
        stock = await session.get(Stock, int(raw_id))

        return stock_ref(stock) if stock is not None else None

    return None


def choice_label(candidate: dict[str, Any]) -> str:

    """How one candidate reads in the question."""

    if candidate["kind"] == "stock":
        return f"{candidate['name']} ({candidate['symbol']}, {candidate['isin']})"

    return f"{candidate['name']} ({candidate['isin']})"
