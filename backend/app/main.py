"""The FastAPI app: builds the planner graph on startup and mounts the API routes."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent import graph as planner
from app.agent.checkpointer import open_checkpointer
from app.api.router import api_router
from app.db.session import engine
from app.features.runs.worker import fail_orphaned_runs


@asynccontextmanager
async def lifespan(app: FastAPI):

    """Compile the graph on the Postgres checkpointer and fail runs a crashed process left active, then close both pools."""

    async with open_checkpointer() as checkpointer:

        planner.planner_graph = planner.build_planner_graph(checkpointer)

        await fail_orphaned_runs()

        yield

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
