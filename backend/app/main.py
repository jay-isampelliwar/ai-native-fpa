"""The FastAPI app: builds the planner graph on startup and mounts the API routes."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver

from app.agent import graph as planner
from app.api.router import api_router
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):

    """Compile the graph before the first request, and close the database pool on shutdown."""

    planner.planner_graph = planner.build_planner_graph(InMemorySaver())

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
