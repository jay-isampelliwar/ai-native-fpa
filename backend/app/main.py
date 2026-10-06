from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.agent import graph as planner



@asynccontextmanager
async def lifespan(app: FastAPI):

    """Open the checkpointer, register skills and compile the graph before the first request is served."""

    await abandon_unfinished_imports()

    async with postgres_checkpointer() as checkpointer:

        planner.planner_graph = planner.build_planner_graph(checkpointer)

        yield

    await dispose_engine()


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
