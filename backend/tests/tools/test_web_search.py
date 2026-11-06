"""Tests for web search: the shared cache key, the Tavily options per freshness, and one Tavily call shared by many callers through real Redis."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest

from app.agent.blocks import sources_block
from app.core.config import get_settings
from app.core.redis import get_redis
from app.features.web_search import service
from app.features.web_search.cache import cache_key, normalize_query
from app.features.web_search.schemas import Freshness, WebSearchUnavailable


PAGE = {"title": "Nifty ends higher", "url": "https://www.moneycontrol.com/news/nifty", "site": "moneycontrol.com", "published": None, "content": "Nifty closed up."}


@pytest.fixture
async def prefix(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[str]:

    """Point the cache at a throwaway key prefix and delete every key under it afterwards."""

    name = f"test:websearch:{uuid4().hex}"

    monkeypatch.setattr(get_settings(), "REDIS_WEB_SEARCH_PREFIX", name)

    yield name

    keys = [key async for key in get_redis().scan_iter(f"{name}:*")]

    if keys:
        await get_redis().delete(*keys)


def counting_fetch(
    calls: list[str],
    results: list[dict[str, Any]],
    delay: float = 0.0,
    ):

    """A fake Tavily fetch that records each call, waits a little, and returns the given results."""

    async def fake(
        query: str,
        options: Any,
        timeout: float,
        ) -> list[dict[str, Any]]:

        """Record the call and return the fixed results."""

        calls.append(query)

        await asyncio.sleep(delay)

        return results

    return fake


def test_normalize_merges_case_spaces_and_end_marks() -> None:

    """Small typing differences clean to the same text."""

    assert normalize_query("  Nifty   50 Today?? ") == "nifty 50 today"
    assert normalize_query("NIFTY 50 today.") == "nifty 50 today"


def test_key_is_shared_but_split_by_freshness() -> None:

    """The same search shares one key, while another freshness group gets its own key."""

    options = service.options_for(Freshness.live)

    assert cache_key("Nifty today?", Freshness.live, options) == cache_key("nifty  today", Freshness.live, options)
    assert cache_key("nifty today", Freshness.live, options) != cache_key("nifty today", Freshness.today, options)


def test_options_follow_freshness() -> None:

    """Live and today search a day of news, recent a week, evergreen a general India search."""

    assert service.options_for(Freshness.live).time_range == "day"
    assert service.options_for(Freshness.recent).time_range == "week"

    evergreen = service.options_for(Freshness.evergreen)

    assert (evergreen.topic, evergreen.time_range, evergreen.country) == ("general", None, "india")


def test_clean_results_keeps_only_web_links() -> None:

    """A javascript link and Tavily's own pages are dropped, and the site loses its www."""

    raw = {
        "results": [
            {"title": "Good", "url": "https://www.livemint.com/a", "content": "text"},
            {"title": "Bad", "url": "javascript:alert(1)", "content": "text"},
            {"title": "nifty", "url": "https://www.tavily.com/search/nifty", "content": "text"},
            ],
        }

    cleaned = service.clean_results(raw)

    assert [item["site"] for item in cleaned] == ["livemint.com"]


def test_sources_block_lists_links_or_nothing() -> None:

    """The card lists each page, and there is no card when nothing was found."""

    block = sources_block({"results": [PAGE]})

    assert block is not None and block["type"] == "sources"
    assert block["items"][0]["url"] == PAGE["url"]
    assert sources_block({"results": []}) is None


async def test_second_search_comes_from_cache(
    prefix: str,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """The first search asks Tavily and saves with the live TTL; the second gets the same result without asking."""

    calls: list[str] = []

    monkeypatch.setattr(service, "fetch", counting_fetch(calls, [PAGE]))

    first = await service.search("Nifty today", Freshness.live, 10)
    second = await service.search("nifty today?", Freshness.live, 10)

    assert calls == ["Nifty today"]
    assert (first["from_cache"], second["from_cache"]) == (False, True)
    assert second["results"] == [PAGE]

    key = cache_key("nifty today", Freshness.live, service.options_for(Freshness.live))

    ttl = await get_redis().ttl(key)

    assert 0 < ttl <= get_settings().WEB_SEARCH_TTL_SECONDS["live"]
    assert json.loads(await get_redis().get(key))["results"] == [PAGE]


async def test_many_callers_at_once_share_one_tavily_call(
    prefix: str,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """Five searches at the same moment make one Tavily call; the rest wait for its result."""

    calls: list[str] = []

    monkeypatch.setattr(service, "fetch", counting_fetch(calls, [PAGE], delay=0.5))

    results = await asyncio.gather(*(service.search("sensex today", Freshness.live, 10) for _ in range(5)))

    assert len(calls) == 1
    assert sorted(result["from_cache"] for result in results) == [False, True, True, True, True]


async def test_empty_result_is_not_cached(
    prefix: str,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """A search that finds nothing is asked again next time, not saved."""

    calls: list[str] = []

    monkeypatch.setattr(service, "fetch", counting_fetch(calls, []))

    await service.search("rare query", Freshness.today, 10)
    await service.search("rare query", Freshness.today, 10)

    assert len(calls) == 2


async def test_failure_frees_the_lock(
    prefix: str,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """When Tavily fails the error reaches the caller and the lock is freed, so the next search is not stuck waiting."""

    async def broken(
        query: str,
        options: Any,
        timeout: float,
        ) -> list[dict[str, Any]]:

        """Fail like an unreachable Tavily."""

        raise WebSearchUnavailable("down")

    monkeypatch.setattr(service, "fetch", broken)

    with pytest.raises(WebSearchUnavailable):
        await service.search("rbi repo rate", Freshness.recent, 10)

    key = cache_key("rbi repo rate", Freshness.recent, service.options_for(Freshness.recent))

    assert await get_redis().exists(f"{key}:lock") == 0
