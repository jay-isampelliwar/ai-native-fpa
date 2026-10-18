"""The FastAPI app: builds the planner graph on startup and mounts the API routes."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.agent import graph as planner
from app.agent.checkpointer import open_checkpointer
from app.api.router import api_router
from app.core.redis import close_redis
from app.db.session import engine
from app.features.memory.worker import consume_forever
from app.features.runs.worker import fail_orphaned_runs


@asynccontextmanager
async def lifespan(app: FastAPI):

    """Compile the graph, fail runs a crashed process left active and start the memory worker, then stop it and close every pool."""

    async with open_checkpointer() as checkpointer:

        planner.planner_graph = planner.build_planner_graph(checkpointer)

        await fail_orphaned_runs()

        memory_task = asyncio.create_task(consume_forever(), name="memory-worker")

        yield

        memory_task.cancel()

        with suppress(asyncio.CancelledError):
            await memory_task

    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="AI Native Financial Planner",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/health")
async def health() -> dict:

    """Report that this process is serving, without touching the database or any model."""

    return {"status": "ok",}
