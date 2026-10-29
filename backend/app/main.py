"""The FastAPI app: mounts the API routes and, when runs execute inline, builds the planner graph on startup."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.agent import graph as planner
from app.agent.checkpointer import open_checkpointer
from app.api.router import api_router
from app.core.redis import close_redis
from app.db.session import engine
from app.features.approvals.sweeper import sweep_forever
from app.features.memory.worker import consume_forever
from app.features.runs.jobs import queued_mode
from app.features.runs.worker import fail_orphaned_runs


async def stop(tasks: list[asyncio.Task]) -> None:

    """Cancel each background task and wait for it to finish."""

    for task in tasks:

        task.cancel()

        with suppress(asyncio.CancelledError):
            await task


@asynccontextmanager
async def lifespan(app: FastAPI):

    """Start the memory worker, and when running runs inline also compile the graph, fail runs a crashed process left active and start the approval sweep."""

    tasks = [asyncio.create_task(consume_forever(), name="memory-worker")]

    if queued_mode():

        yield

        await stop(tasks)

    else:

        async with open_checkpointer() as checkpointer:

            planner.planner_graph = planner.build_planner_graph(checkpointer)

            await fail_orphaned_runs()

            tasks.append(asyncio.create_task(sweep_forever(), name="approval-sweep"))

            yield

            await stop(tasks)

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
