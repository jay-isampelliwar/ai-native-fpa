"""The FastAPI app: mounts the API routes; runs, memories and sweeps happen in their own worker services."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.redis import close_redis
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):

    """Serve requests only, since every background worker runs as its own service, and close every pool on shutdown."""

    yield

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
