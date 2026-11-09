"""Quote indices: answer from the shared Redis cache when it can, else read Yahoo's daily bars and save the quote until it goes stale."""

import asyncio
import logging
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings
from app.features.indices.schemas import DISPLAY_NAMES, YAHOO_SYMBOLS, IndexName, IndexQuote, QuoteUnavailable
from app.features.web_search.cache import read_result, save_result
from app.observability.observations import observe_step, update_step


IST = ZoneInfo("Asia/Kolkata")

MARKET_OPENS = (9, 15)

WEEKEND = (5, 6)

MIN_TTL_SECONDS = 60

USER_AGENT = "Mozilla/5.0 (compatible; ai-native-fpa/1.0)"

YAHOO_STEP = "yahoo.chart"

log = logging.getLogger(__name__)


def quote_key(index: IndexName) -> str:

    """The shared Redis key for one index's quote."""

    return f"{get_settings().REDIS_INDEX_QUOTE_PREFIX}:{index.value}"


def is_open(
    quote: IndexQuote,
    now: datetime,
    ) -> bool:

    """Say whether the market is in its regular session at this moment."""

    return quote.session_start <= now.timestamp() < quote.session_end


def next_open(now: datetime) -> datetime:

    """The next weekday 9:15 am IST after this moment; a market holiday just means one early refresh."""

    local = now.astimezone(IST)

    candidate = local.replace(hour=MARKET_OPENS[0], minute=MARKET_OPENS[1], second=0, microsecond=0)

    if candidate <= local:
        candidate += timedelta(days=1)

    while candidate.weekday() in WEEKEND:
        candidate += timedelta(days=1)

    return candidate


def ttl_for(
    quote: IndexQuote,
    now: datetime,
    ) -> int:

    """Keep a quote one minute while the market is open, and until the next open while it is closed."""

    if is_open(quote, now):
        return get_settings().INDEX_QUOTE_OPEN_TTL_SECONDS

    return max(int((next_open(now) - now).total_seconds()), MIN_TTL_SECONDS)


def two_places(value: Any) -> float | None:

    """Round Yahoo's float to two decimals, since it sends 24536.599609375 for 24536.60."""

    if value is None:
        return None

    return round(float(value), 2)


def parse_chart(
    index: IndexName,
    body: dict[str, Any],
    ) -> IndexQuote:

    """Build a quote from Yahoo's daily bars, taking the previous close from the bar before the last, since its own previousClose field can be days old."""

    try:

        result = body["chart"]["result"][0]
        meta = result["meta"]
        bars = result["indicators"]["quote"][0]
        period = meta["currentTradingPeriod"]["regular"]

        days = [
            (bars["open"][i], bars["high"][i], bars["low"][i], bars["close"][i])
            for i in range(len(result["timestamp"]))
            if bars["open"][i] is not None
            ]

        previous_close = days[-2][3]

        if previous_close is None:
            raise QuoteUnavailable(f"{index.value}: no previous close")

        return IndexQuote(
            index=index,
            name=DISPLAY_NAMES[index],
            value=two_places(meta["regularMarketPrice"]),
            previous_close=two_places(previous_close),
            open=two_places(days[-1][0]),
            high=two_places(days[-1][1]),
            low=two_places(days[-1][2]),
            as_of=int(meta["regularMarketTime"]),
            session_start=int(period["start"]),
            session_end=int(period["end"]),
            )

    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise QuoteUnavailable(f"{index.value}: unexpected chart data") from exc


async def fetch_quote(
    index: IndexName,
    timeout: float,
    ) -> IndexQuote:

    """Read one index's last five daily bars from Yahoo inside a step that records the HTTP status, and turn them into a quote."""

    url = f"{get_settings().YAHOO_CHART_URL}/{YAHOO_SYMBOLS[index]}"

    async with observe_step(get_settings(), YAHOO_STEP, "span", {"provider": "yahoo", "index": index.value}) as step:

        try:

            async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
                response = await client.get(url, params={"range": "5d", "interval": "1d"})

            update_step(step, metadata={"http_status": response.status_code})

            response.raise_for_status()

            body = response.json()

        except (httpx.HTTPError, ValueError) as exc:

            update_step(step, metadata={"cause": type(exc).__name__})

            raise QuoteUnavailable(f"{index.value}: {exc}") from exc

    return parse_chart(index, body)


async def quote(
    index: IndexName,
    timeout: float,
    ) -> IndexQuote:

    """Return one index's quote from the shared cache, or fetch it from Yahoo and save it for everyone."""

    saved = await read_result(quote_key(index))

    if saved is not None:

        try:
            return IndexQuote(**{**saved, "index": IndexName(saved["index"])})

        except (KeyError, TypeError, ValueError):
            log.warning("index quote cache held a broken value for %s", index.value)

    fresh = await fetch_quote(index, timeout)

    await save_result(quote_key(index), asdict(fresh), ttl_for(fresh, datetime.now(IST)))

    return fresh


async def quotes(
    indices: list[IndexName],
    time_budget: float,
    ) -> tuple[list[IndexQuote], list[IndexName]]:

    """Quote every asked index at once, returning the quotes in the asked order and the indices that failed."""

    timeout = max(min(get_settings().INDEX_QUOTE_TIMEOUT_SECONDS, time_budget - 1), 1.0)

    asked = list(dict.fromkeys(indices))

    results = await asyncio.gather(*(quote(index, timeout) for index in asked), return_exceptions=True)

    found: list[IndexQuote] = []
    failed: list[IndexName] = []

    for index, result in zip(asked, results, strict=True):

        if isinstance(result, IndexQuote):
            found.append(result)

            continue

        log.warning("index quote failed for %s: %s", index.value, result)

        failed.append(index)

    return found, failed
