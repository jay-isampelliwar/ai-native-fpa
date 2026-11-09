"""Small Langfuse steps around plain code inside a graph node that the LangChain callback cannot see, carrying counts only and never failing the caller."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AbstractContextManager, asynccontextmanager
from typing import Any, Literal

from langfuse import LangfuseGuardrail, LangfuseRetriever, LangfuseSpan
from langgraph.errors import GraphBubbleUp

from app.core.config import Settings
from app.observability.langfuse import create_langfuse


type Step = LangfuseSpan | LangfuseRetriever | LangfuseGuardrail

type StepType = Literal["span", "retriever", "guardrail"]

type StepScope = tuple[AbstractContextManager[Step], Step]

log = logging.getLogger(__name__)

PAUSED = "paused"
CANCELLED = "cancelled"


def open_step(
    settings: Settings,
    name: str,
    as_type: StepType,
    metadata: dict[str, Any] | None = None,
    ) -> StepScope | None:

    """Start a step as the current span under the node running now, so steps inside it nest, or None when tracing is off or it fails to start."""

    client = create_langfuse(settings)

    if client is None:
        return None

    try:
        scope = client.start_as_current_observation(name=name, as_type=as_type, metadata=metadata or {})

        return scope, scope.__enter__()

    except Exception:

        log.exception("Langfuse step %s failed to start, so it is not traced", name)

        return None


def update_step(
    step: Step | None,
    **fields: Any,
    ) -> None:

    """Add metadata, a level or a status message to a step, doing nothing without one and logging instead of raising."""

    if step is None:
        return

    try:
        step.update(**fields)

    except Exception:
        log.exception("Langfuse step failed to update")


def end_step(scope: StepScope | None) -> None:

    """Close a step so it is sent and its parent is current again, doing nothing without one and logging instead of raising."""

    if scope is None:
        return

    try:
        scope[0].__exit__(None, None, None)

    except Exception:
        log.exception("Langfuse step failed to end")


@asynccontextmanager
async def observe_step(
    settings: Settings,
    name: str,
    as_type: StepType,
    metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[Step | None]:

    """Wrap a block in a step, marking a pause for the user as paused, a cut-off as a cancelled warning, and any other crash as an error by its type alone, then close it."""

    scope = open_step(settings, name, as_type, metadata)
    step = scope[1] if scope is not None else None

    try:
        yield step

    except GraphBubbleUp:

        update_step(step, metadata={"outcome": PAUSED})

        raise

    except asyncio.CancelledError:

        update_step(step, level="WARNING", status_message=CANCELLED)

        raise

    except Exception as exc:

        update_step(step, level="ERROR", status_message=type(exc).__name__)

        raise

    finally:
        end_step(scope)
