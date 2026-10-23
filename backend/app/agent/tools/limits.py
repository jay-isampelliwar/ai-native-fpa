"""Time limits for tools inside one turn: how long a try may take, how long the database may work, and when a retry is safe."""

import math
import random
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import PlannerContext
from app.agent.tools.policies import Risk, policy_for
from app.agent.tools.results import ToolResult, retryable
from app.core.config import get_settings
from app.db.session import SessionLocal


RETRYABLE_ERRORS = (TimeoutError, OperationalError)

TIMEOUT_TEXT = "The database took too long to answer, so this may not have been saved."

UNAVAILABLE_TEXT = "Could not reach the database, so this may not have been saved."


def turn_deadline() -> float:

    """The moment, on the monotonic clock, by which a turn starting now must finish."""

    return time.monotonic() + get_settings().TURN_TIMEOUT_SECONDS


def time_left(context: PlannerContext | None) -> float:

    """Seconds until the turn's deadline, or forever outside a run that has one."""

    if context is None or context.deadline is None:
        return math.inf

    return max(context.deadline - time.monotonic(), 0.0)


def tool_timeout(context: PlannerContext | None) -> float:

    """How long one try of a tool may take: its own limit, or the turn's remaining time when that is shorter."""

    return min(get_settings().TOOL_TIMEOUT_SECONDS, time_left(context))


def statement_timeout_ms(context: PlannerContext | None) -> int:

    """How long one database statement may run: its own limit, or the turn's remaining time when that is shorter."""

    limit = get_settings().DB_STATEMENT_TIMEOUT_MS

    return max(1, math.floor(min(limit, time_left(context) * 1000)))


@asynccontextmanager
async def tool_session(context: PlannerContext | None) -> AsyncIterator[AsyncSession]:

    """Open a tool's session with a statement timeout set for its transaction, so Postgres stops a stuck query itself."""

    async with SessionLocal() as session:

        await session.execute(text(f"SET LOCAL statement_timeout = {statement_timeout_ms(context)}"))

        yield session


def can_retry(
    tool_name: str,
    context: PlannerContext | None,
    ) -> bool:

    """Reads may always run again; writes only inside a conversation, where the idempotency guard stops a second write."""

    policy = policy_for(tool_name)

    if policy is not None and policy.risk == Risk.read:
        return True

    return context is not None and context.conversation_id is not None


def retry_wait(attempt: int) -> float:

    """The pause before the next try: doubling from the base, with a little jitter so retries do not line up."""

    base = get_settings().TOOL_RETRY_BASE_SECONDS

    return base * (2 ** attempt) + random.uniform(0, base / 2)


def worth_retrying(
    context: PlannerContext | None,
    wait: float,
    ) -> bool:

    """Say whether enough of the turn is left, after the wait, to give another try a fair chance."""

    return time_left(context) - wait >= get_settings().MIN_RETRY_SECONDS


def classify(exc: BaseException) -> ToolResult:

    """Turn a retryable failure into its result: a timeout or a database that could not be reached."""

    if isinstance(exc, TimeoutError):
        return retryable(TIMEOUT_TEXT, "database_timeout")

    return retryable(UNAVAILABLE_TEXT, "db_unavailable")
