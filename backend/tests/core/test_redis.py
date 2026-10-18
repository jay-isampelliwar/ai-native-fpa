"""Tests that the shared Redis client reaches the real Redis named in REDIS_URL."""

from app.core.redis import close_redis, get_redis
from app.features.memory.worker import BLOCK_MS


async def test_get_redis_pings_real_redis() -> None:

    """Ping the real Redis through the shared client and close it afterwards."""

    try:
        assert await get_redis().ping() is True

    finally:
        await close_redis()


async def test_read_timeout_outlasts_worker_block() -> None:

    """The client's read timeout is longer than the worker's XREADGROUP block, so an empty wait is not an error."""

    connection = await get_redis().connection_pool.get_connection()

    try:
        assert connection.socket_timeout * 1000 > BLOCK_MS

    finally:
        await get_redis().connection_pool.release(connection)


async def test_get_redis_returns_same_client() -> None:

    """Return the same cached client on every call until close_redis() clears it."""

    try:
        assert get_redis() is get_redis()

    finally:
        await close_redis()
