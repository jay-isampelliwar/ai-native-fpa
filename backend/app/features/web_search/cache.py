"""The Redis side of web search: the cache key, reading and saving results, and the lock that lets one caller search for many."""

import asyncio
import hashlib
import json
import logging
import re
import time
import unicodedata
import uuid
from dataclasses import asdict
from typing import Any

from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.redis import get_redis
from app.features.web_search.schemas import Freshness, SearchOptions


KEY_VERSION = 4

POLL_SECONDS = 0.25

SPACES = re.compile(r"\s+")

END_MARKS = "?!.,;: "

RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

log = logging.getLogger(__name__)


def normalize_query(query: str) -> str:

    """Lowercase the query, fold look-alike characters, merge spaces and drop end marks, so small typing differences share a key."""

    folded = unicodedata.normalize("NFKC", query).lower()

    return SPACES.sub(" ", folded).strip().strip(END_MARKS).strip()


def cache_key(
    query: str,
    freshness: Freshness,
    options: SearchOptions,
    ) -> str:

    """Hash the cleaned query, its freshness and every search option into one shared key with no user in it."""

    canonical = json.dumps(
        {"v": KEY_VERSION, "query": normalize_query(query), "freshness": freshness.value, **asdict(options)},
        sort_keys=True,
        separators=(",", ":"),
        )

    digest = hashlib.sha256(canonical.encode()).hexdigest()

    return f"{get_settings().REDIS_WEB_SEARCH_PREFIX}:{digest}"


def lock_key(key: str) -> str:

    """The lock key that sits beside a result key."""

    return f"{key}:lock"


async def read_result(key: str) -> dict[str, Any] | None:

    """Return the saved result for the key, or None when it is missing, expired, broken or Redis is down."""

    try:
        raw = await get_redis().get(key)

    except RedisError:

        log.warning("web search cache read failed", exc_info=True)

        return None

    if raw is None:
        return None

    try:
        return json.loads(raw)

    except ValueError:

        log.warning("web search cache held a broken value for %s", key)

        return None


async def save_result(
    key: str,
    result: dict[str, Any],
    ttl_seconds: int,
    ) -> None:

    """Save the result under the key until its time runs out, logging and moving on when Redis is down."""

    try:
        await get_redis().set(key, json.dumps(result), ex=ttl_seconds)

    except RedisError:
        log.warning("web search cache write failed", exc_info=True)


async def take_lock(key: str) -> str | None:

    """Take the search lock for the key and return its token, or None when another caller holds it or Redis is down."""

    token = uuid.uuid4().hex

    try:
        taken = await get_redis().set(lock_key(key), token, nx=True, ex=get_settings().WEB_SEARCH_LOCK_SECONDS)

    except RedisError:

        log.warning("web search lock failed", exc_info=True)

        return None

    return token if taken else None


async def release_lock(
    key: str,
    token: str,
    ) -> None:

    """Free the lock only if this caller still holds it, so a slow caller never frees someone else's lock."""

    try:
        await get_redis().eval(RELEASE_SCRIPT, 1, lock_key(key), token)

    except RedisError:
        log.warning("web search lock release failed", exc_info=True)


async def lock_is_held(key: str) -> bool:

    """Say whether another caller holds the lock, treating a Redis error as not held so the caller searches itself."""

    try:
        return bool(await get_redis().exists(lock_key(key)))

    except RedisError:
        return False


async def wait_for_result(
    key: str,
    seconds: float,
    ) -> dict[str, Any] | None:

    """Poll for the result another caller is fetching, until it lands, their lock goes, or the wait runs out."""

    end = time.monotonic() + seconds

    while time.monotonic() < end:

        await asyncio.sleep(POLL_SECONDS)

        result = await read_result(key)

        if result is not None:
            return result

        if not await lock_is_held(key):
            return None

    return None
