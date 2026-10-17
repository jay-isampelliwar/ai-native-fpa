"""The Postgres checkpointer that keeps each conversation's graph state across restarts and deploys."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.db.session import database_url


CHECKPOINT_TABLES = frozenset({
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
    })

POOL_MAX_SIZE = 10


def checkpointer_url() -> str:

    """Return the database URL in plain libpq form, since psycopg does not read the SQLAlchemy driver prefix."""

    return database_url().replace("postgresql+psycopg://", "postgresql://", 1)


@asynccontextmanager
async def open_checkpointer() -> AsyncGenerator[AsyncPostgresSaver, None]:

    """Open a connection pool, create the checkpoint tables if missing, and close the pool on exit."""

    pool = AsyncConnectionPool(
        checkpointer_url(),
        max_size=POOL_MAX_SIZE,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": None, "row_factory": dict_row},
        )

    await pool.open()

    try:

        checkpointer = AsyncPostgresSaver(pool)

        await checkpointer.setup()

        yield checkpointer

    finally:

        await pool.close()
