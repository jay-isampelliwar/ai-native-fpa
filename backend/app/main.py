"""The ASGI application: wiring, startup order, and nothing else.

This file deliberately contains no business logic. Its whole job is to decide what exists
by the time the first request arrives, and the order matters more than the contents.

Skills are registered during startup rather than at import time. The registry is the
closed set the router may choose from, so it has to be populated before any request can
route - but doing it in a lifespan hook rather than at module import keeps tests free to
build isolated registries without inheriting the production one.

The graph is compiled during startup too, not on first request. Compiling it eagerly
means a wiring mistake fails the deploy rather than the first user's message, and it also
warms the checkpointer connection before it is needed.

The PostgreSQL checkpointer is opened for the life of the application rather than per
request, and it is the only checkpointer this service uses. A run paused for approval is
resumed by a later request - often minutes later, possibly after a deploy - so the saver
holding that state has to outlive the request that created it and the process it started in.

There is no in-memory fallback. If PostgreSQL is unreachable the application fails to start,
which is the correct outcome: a planner serving requests with throwaway approval state would
lose a pending instruction silently rather than loudly.

Shutdown disposes the connection pool. Without it a reload during development leaks
connections until PostgreSQL refuses new ones, which presents as an unrelated failure an
hour later.

``/health`` is intentionally trivial and does not touch the database or a model. It
answers whether this process is alive, which is what a load balancer is asking; a probe
that calls a paid API turns an outage into a bill.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.checkpointer import postgres_checkpointer
from app.db.session import dispose_engine
from app.agent import graph as planner


async def abandon_unfinished_imports() -> None:

    """Fail imports a stopped process left mid read, so nothing polls a background job that no longer exists."""

    from app.services.import_service import import_service

    try:
        await import_service.abandon_unfinished()

    except Exception:
        pass


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
    debug=settings.debug,
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/health")
async def health() -> dict:

    """Report that this process is serving, without touching the database or any model."""

    return {"status": "ok", "environment": settings.environment}
