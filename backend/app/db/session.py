"""The async database engine, the session factory and the declarative base for every model."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


def database_url() -> str:

    """Return the configured URL on the psycopg 3 driver, failing loudly when it is missing."""

    settings = get_settings()

    url = settings.DATABASE_URL

    if url is None:
        raise RuntimeError("DATABASE_URL is not set")

    if url.startswith("postgresql+"):
        return url

    return url.replace("postgresql://", "postgresql+psycopg://", 1)


engine = create_async_engine(
    database_url(),
    pool_pre_ping=True,
    connect_args={"connect_timeout": get_settings().DB_CONNECT_TIMEOUT_SECONDS},
    )

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    )


async def get_session() -> AsyncIterator[AsyncSession]:

    """Give one request its own session and close it when the request is done."""

    async with SessionLocal() as session:
        yield session


class Base(DeclarativeBase):

    """The parent class every table model extends."""
