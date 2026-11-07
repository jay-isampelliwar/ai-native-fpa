"""Shared fixtures: a temp user with one run, a throwaway Redis stream, no real intent model, no Langfuse traces, and closing both pools after every test."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from app.agent import intents
from app.core.config import get_settings
from app.core.redis import close_redis, get_redis
from app.db.session import engine
from tests.support import SeededRun, create_user, delete_user_data, seed_run


@pytest.fixture(autouse=True)
def no_intent_model(monkeypatch: pytest.MonkeyPatch) -> None:

    """Answer every intent model call with the fallback and no tokens, so no test calls OpenAI or counts its tokens."""

    async def fallback(messages: list) -> tuple[list[str], None]:

        """The fallback intents, with no raw answer."""

        return list(intents.FALLBACK_INTENTS), None

    monkeypatch.setattr(intents, "classify_with_model", fallback)


@pytest.fixture(autouse=True)
def no_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:

    """Blank the Langfuse public key on the shared settings, so no test sends a trace even when .env has real keys."""

    monkeypatch.setattr(get_settings(), "LANGFUSE_PUBLIC_KEY", None)


@pytest.fixture(autouse=True)
async def close_pools() -> AsyncIterator[None]:

    """Close Redis and the DB pool after each test, so no connection outlives the test's event loop."""

    yield

    await close_redis()
    await engine.dispose()


@pytest.fixture
async def seeded_run() -> AsyncIterator[SeededRun]:

    """Give the test a temp user with one queued run, then delete everything that user owns."""

    user_id = await create_user()

    try:
        yield await seed_run(user_id)

    finally:
        await delete_user_data(user_id)


@pytest.fixture
async def redis_stream() -> AsyncIterator[str]:

    """Give the test its own Redis stream name, then delete it and its dead stream."""

    name = f"ai-native-fpa:test:{uuid4().hex}"

    try:
        yield name

    finally:
        await get_redis().delete(name, f"{name}:dead")
