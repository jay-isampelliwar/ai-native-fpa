"""Run one web search: answer from the shared Redis cache when it can, else ask Tavily once and save the result for everyone."""

import logging
import time
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from tavily import AsyncTavilyClient

from app.core.config import get_settings
from app.features.web_search import cache
from app.features.web_search.preview import add_images
from app.features.web_search.schemas import Freshness, SearchOptions, WebSearchUnavailable
from app.observability.observations import observe_step, update_step


SAFE_SCHEMES = ("http", "https")

SKIPPED_SITES = ("tavily.com",)

MIN_TAVILY_SECONDS = 2.0

TAVILY_STEP = "tavily.search"

log = logging.getLogger(__name__)


@lru_cache
def tavily_client() -> AsyncTavilyClient | None:

    """Build the Tavily client once from TAVILY_API_KEY, or None when no key is set."""

    key = get_settings().TAVILY_API_KEY

    if key is None or not key.get_secret_value():
        return None

    return AsyncTavilyClient(api_key=key.get_secret_value())


def options_for(freshness: Freshness) -> SearchOptions:

    """The Tavily options for a freshness group: news within a day or week, or a general search for lasting facts."""

    settings = get_settings()

    if freshness == Freshness.evergreen:
        return SearchOptions("general", None, settings.WEB_SEARCH_COUNTRY, settings.WEB_SEARCH_DEPTH, settings.WEB_SEARCH_MAX_RESULTS)

    time_range = "week" if freshness == Freshness.recent else "day"

    return SearchOptions("news", time_range, None, settings.WEB_SEARCH_DEPTH, settings.WEB_SEARCH_MAX_RESULTS)


def site_of(url: str) -> str:

    """The site name of a link without its www, such as 'economictimes.indiatimes.com'."""

    host = urlparse(url).hostname or ""

    return host.removeprefix("www.")


def trim(
    text: str,
    limit: int,
    ) -> str:

    """Cut the text to the limit on a word boundary, adding an ellipsis when it was cut."""

    text = " ".join(text.split())

    if len(text) <= limit:
        return text

    return text[:limit].rsplit(" ", 1)[0] + "…"


def clean_results(raw: dict[str, Any]) -> list[dict[str, Any]]:

    """Keep only http links from Tavily's answer, each with its title, site, date and a short piece of its text."""

    limit = get_settings().WEB_SEARCH_CONTENT_CHARS

    results = []

    for item in raw.get("results", []):

        url = str(item.get("url") or "")

        if urlparse(url).scheme not in SAFE_SCHEMES:
            continue

        if site_of(url).endswith(SKIPPED_SITES):
            continue

        results.append({
            "title": trim(str(item.get("title") or site_of(url)), 200),
            "url": url,
            "site": site_of(url),
            "published": item.get("published_date"),
            "content": trim(str(item.get("content") or ""), limit),
            })

    return results


async def fetch(
    query: str,
    options: SearchOptions,
    timeout: float,
    ) -> list[dict[str, Any]]:

    """Ask Tavily for pages only, no written answer, inside a step that records the result count, and return the cleaned results."""

    client = tavily_client()

    if client is None:
        raise WebSearchUnavailable("TAVILY_API_KEY is not set")

    async with observe_step(get_settings(), TAVILY_STEP, "span", {"provider": "tavily", "topic": options.topic}) as step:

        try:

            raw = await client.search(
                query,
                topic=options.topic,
                time_range=options.time_range,
                country=options.country,
                search_depth=options.search_depth,
                max_results=options.max_results,
                include_answer=False,
                include_raw_content=False,
                include_images=False,
                timeout=timeout,
                )

        except Exception as exc:

            update_step(step, metadata={"cause": type(exc).__name__})

            raise WebSearchUnavailable(str(exc)) from exc

        results = clean_results(raw)

        update_step(step, metadata={"result_count": len(results)})

    return results


async def search(
    query: str,
    freshness: Freshness,
    time_budget: float,
    ) -> dict[str, Any]:

    """Return the shared cached result for this search, or wait for the caller already fetching it, or fetch it from Tavily and cache it."""

    settings = get_settings()

    started = time.monotonic()

    options = options_for(freshness)

    key = cache.cache_key(query, freshness, options)

    saved = await cache.read_result(key)

    if saved is not None:

        log.info("web search cache hit freshness=%s", freshness.value)

        return {**saved, "from_cache": True}

    token = await cache.take_lock(key)

    if token is None:

        wait = min(settings.WEB_SEARCH_WAIT_SECONDS, max(time_budget - MIN_TAVILY_SECONDS - 1, 0))

        saved = await cache.wait_for_result(key, wait)

        if saved is not None:

            log.info("web search cache hit after wait freshness=%s", freshness.value)

            return {**saved, "from_cache": True}

    try:

        timeout = max(min(settings.WEB_SEARCH_TIMEOUT_SECONDS, time_budget - 1), MIN_TAVILY_SECONDS)

        results = await fetch(query, options, timeout)

        left = time_budget - (time.monotonic() - started) - 1

        await add_images(results, min(settings.WEB_PREVIEW_TIMEOUT_SECONDS, left))

        result = {
            "query": cache.normalize_query(query),
            "freshness": freshness.value,
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "results": results,
            }

        if results:
            await cache.save_result(key, result, settings.WEB_SEARCH_TTL_SECONDS[freshness.value])

        log.info("web search cache miss freshness=%s results=%d", freshness.value, len(results))

    finally:

        if token is not None:
            await cache.release_lock(key, token)

    return {**result, "from_cache": False}
