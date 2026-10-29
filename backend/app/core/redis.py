"""The shared async Redis client and the stream helpers used by the outbox publisher, the memory worker and the agent worker."""

import os
import socket
from functools import lru_cache

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.core.config import get_settings


StreamEntry = tuple[str, dict[str, str]]

SOCKET_TIMEOUT_SECONDS = 30


def process_name() -> str:

    """Name this process uniquely as hostname:pid, the name it reads a stream under; Docker gives every container its own hostname."""

    return f"{socket.gethostname()}:{os.getpid()}"


@lru_cache
def get_redis() -> Redis:

    """Build the Redis client once from REDIS_URL and reuse it, with a read timeout longer than any XREADGROUP block."""

    return Redis.from_url(
        get_settings().REDIS_URL,
        decode_responses=True,
        socket_timeout=SOCKET_TIMEOUT_SECONDS,
        )


async def close_redis() -> None:

    """Close the shared client's connections and forget it, so the next get_redis() builds a fresh one."""

    if get_redis.cache_info().currsize == 0:
        return

    await get_redis().aclose()

    get_redis.cache_clear()


async def publish_event(
    stream: str,
    fields: dict[str, str],
    ) -> str:

    """Append one entry to the end of a Redis stream with XADD and return the id Redis gave it."""

    return await get_redis().xadd(stream, fields)


async def ensure_group(
    stream: str,
    group: str,
    ) -> None:

    """Create the consumer group from the start of the stream, making the stream if missing, and do nothing if it exists."""

    try:
        await get_redis().xgroup_create(stream, group, id="0", mkstream=True)

    except ResponseError as exc:

        if "BUSYGROUP" not in str(exc):
            raise


async def read_group(
    stream: str,
    group: str,
    consumer: str,
    count: int,
    block_ms: int | None,
    start_id: str = ">",
    ) -> list[StreamEntry]:

    """Read up to count entries with XREADGROUP: new ones with start_id ">", or this consumer's own pending ones after start_id."""

    response = await get_redis().xreadgroup(group, consumer, {stream: start_id}, count=count, block=block_ms)

    if not response:
        return []

    return [(entry_id, fields or {}) for entry_id, fields in response[0][1]]


async def claim_stale(
    stream: str,
    group: str,
    consumer: str,
    min_idle_ms: int,
    count: int,
    ) -> list[StreamEntry]:

    """Take over up to count entries another delivery left unacknowledged for at least min_idle_ms, with XAUTOCLAIM."""

    _, entries, *_ = await get_redis().xautoclaim(stream, group, consumer, min_idle_ms, start_id="0-0", count=count)

    return entries


async def delivery_count(
    stream: str,
    group: str,
    entry_id: str,
    ) -> int:

    """Return how many times the group has handed out this pending entry, or 0 if it is no longer pending."""

    pending = await get_redis().xpending_range(stream, group, min=entry_id, max=entry_id, count=1)

    if not pending:
        return 0

    return pending[0]["times_delivered"]


async def ack(
    stream: str,
    group: str,
    entry_id: str,
    ) -> None:

    """Tell the group this entry is done with XACK, so it is never handed out again."""

    await get_redis().xack(stream, group, entry_id)


async def prune_consumers(
    stream: str,
    group: str,
    keep: str,
    idle_ms: int,
    ) -> list[str]:

    """Delete the group's consumers, other than keep, idle for at least idle_ms with no pending entries, and return their names."""

    pruned = []

    for consumer in await get_redis().xinfo_consumers(stream, group):

        name = consumer["name"]

        if name == keep or consumer["pending"] > 0 or consumer["idle"] < idle_ms:
            continue

        await get_redis().xgroup_delconsumer(stream, group, name)

        pruned.append(name)

    return pruned
