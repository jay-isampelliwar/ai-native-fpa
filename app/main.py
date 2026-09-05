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

``/health`` is intentionally trivial and does not touch the database or a model. It
answers whether this process is alive, which is what a load balancer is asking; a probe
that calls a paid API turns an outage into a bill.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.graphs.orchestrator.graph import get_planner_graph
from app.graphs.skills.bootstrap import register_skills


@asynccontextmanager
async def lifespan(app: FastAPI):

    """Register every approved skill and compile the graph before the first request is served."""

    register_skills()

    get_planner_graph()

    yield


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
