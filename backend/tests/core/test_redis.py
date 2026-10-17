"""Tests that the shared Redis client reaches the real Redis named in REDIS_URL."""

from app.core.redis import close_redis, get_redis


async def test_get_redis_pings_real_redis() -> None:

    """Ping the real Redis through the shared client and close it afterwards."""

    try:
        assert await get_redis().ping() is True

    finally:
        await close_redis()


async def test_get_redis_returns_same_client() -> None:

    """Return the same cached client on every call until close_redis() clears it."""

    try:
        assert get_redis() is get_redis()

    finally:
        await close_redis()
