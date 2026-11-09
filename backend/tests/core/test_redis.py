"""Tests that the shared Redis client reaches the real Redis named in REDIS_URL, and that old idle consumers are pruned."""

from app.core.config import get_settings
from app.core.redis import close_redis, ensure_group, get_redis, process_name, prune_consumers


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
        assert connection.socket_timeout * 1000 > get_settings().REDIS_BLOCK_MS

    finally:
        await get_redis().connection_pool.release(connection)


async def test_get_redis_returns_same_client() -> None:

    """Return the same cached client on every call until close_redis() clears it."""

    try:
        assert get_redis() is get_redis()

    finally:
        await close_redis()


def test_process_name_is_hostname_and_pid() -> None:

    """The consumer name is this machine's hostname and this process's id."""

    hostname, pid = process_name().rsplit(":", 1)

    assert hostname
    assert pid.isdigit()


async def test_prune_deletes_only_idle_consumers_without_work(redis_stream: str) -> None:

    """Pruning removes a consumer with nothing pending, and keeps the given one and any with pending entries."""

    group = "prune-test"

    await ensure_group(redis_stream, group)
    await get_redis().xadd(redis_stream, {"n": "1"})

    await get_redis().xreadgroup(group, "busy", {redis_stream: ">"}, count=1)
    await get_redis().xreadgroup(group, "empty", {redis_stream: ">"}, count=1)
    await get_redis().xreadgroup(group, "me", {redis_stream: ">"}, count=1)

    pruned = await prune_consumers(redis_stream, group, "me", 0)

    names = {consumer["name"] for consumer in await get_redis().xinfo_consumers(redis_stream, group)}

    assert pruned == ["empty"]
    assert names == {"busy", "me"}
