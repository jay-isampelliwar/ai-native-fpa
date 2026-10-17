"""The shared async Redis client used by the outbox publisher and the memory worker."""

from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_settings


@lru_cache
def get_redis() -> Redis:

    """Build the Redis client once from REDIS_URL and reuse it, connecting lazily on the first command."""

    return Redis.from_url(get_settings().REDIS_URL, decode_responses=True)


async def close_redis() -> None:

    """Close the shared client's connections and forget it, so the next get_redis() builds a fresh one."""

    if get_redis.cache_info().currsize == 0:
        return

    await get_redis().aclose()

    get_redis.cache_clear()
