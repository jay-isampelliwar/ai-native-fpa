"""The database engine and the rule that one request gets one transaction.

Everything that touches PostgreSQL goes through ``session_scope``. It opens a session,
yields it, commits if the body returned normally and rolls back if anything raised. A
repository therefore never commits: it reads and it stages changes, and whether those
changes survive is decided by whoever opened the scope. Two writes inside one request
either both land or neither does.

That matters most on the write path we are building towards. Executing an approved change
means inserting a row, updating a status and writing an audit record, and a partial
version of that is worse than a failure - it produces a change nobody can explain or a
record of a change that never happened.

The engine is created once per process and pooled. ``pool_pre_ping`` costs a round trip on
checkout and is worth it here: a planner sits idle between a proposal and an approval, and
a connection killed by a restart or an idle timeout in that window would otherwise surface
as a failure at the exact moment the user pressed approve.

The URL is rewritten to the asyncpg style psycopg driver rather than accepting whatever the
environment supplies. LangGraph's checkpointer wants the plain ``postgresql://`` form and
SQLAlchemy wants a driver named in the scheme, so one setting serves both and neither is
configured by hand.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def async_database_url() -> str:

    """Rewrite the configured URL onto the async driver, so one setting serves the checkpointer too."""

    url = settings.database_url.get_secret_value()

    if url.startswith("postgresql+"):
        return url

    return url.replace("postgresql://", "postgresql+psycopg://", 1)


@lru_cache
def get_engine() -> AsyncEngine:

    """Build the pooled engine once per process, pre-pinging so idle connections fail on checkout."""

    return create_async_engine(
        async_database_url(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        echo=settings.debug and settings.environment == "development",
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:

    """Return the session factory, configured to keep objects usable after a commit."""

    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:

    """Run one unit of work, committing on success and rolling back on any exception."""

    session = get_sessionmaker()()

    try:
        yield session

        await session.commit()

    except Exception:

        await session.rollback()

        raise

    finally:

        await session.close()


async def dispose_engine() -> None:

    """Close every pooled connection, called on application shutdown."""

    await get_engine().dispose()
