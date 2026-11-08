"""Small Langfuse steps around plain code inside a graph node that the LangChain callback cannot see, carrying counts only and never failing the caller."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from langfuse import LangfuseGuardrail, LangfuseRetriever, LangfuseSpan
from langgraph.errors import GraphBubbleUp

from app.core.config import Settings
from app.observability.langfuse import create_langfuse


type Step = LangfuseSpan | LangfuseRetriever | LangfuseGuardrail

type StepType = Literal["span", "retriever", "guardrail"]

log = logging.getLogger(__name__)

PAUSED = "paused"


def open_step(
    settings: Settings,
    name: str,
    as_type: StepType,
    metadata: dict[str, Any] | None = None,
    ) -> Step | None:

    """Start a step under the node running now, or None when tracing is off or the step fails to start."""

    client = create_langfuse(settings)

    if client is None:
        return None

    try:
        return client.start_observation(name=name, as_type=as_type, metadata=metadata or {})

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


def end_step(step: Step | None) -> None:

    """Close a step so it is sent, doing nothing without one and logging instead of raising."""

    if step is None:
        return

    try:
        step.end()

    except Exception:
        log.exception("Langfuse step failed to end")


@asynccontextmanager
async def observe_step(
    settings: Settings,
    name: str,
    as_type: StepType,
    metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[Step | None]:

    """Wrap a block in a step, marking a pause for the user as paused and any other crash as an error by its type alone, then close it."""

    step = open_step(settings, name, as_type, metadata)

    try:
        yield step

    except GraphBubbleUp:

        update_step(step, metadata={"outcome": PAUSED})

        raise

    except Exception as exc:

        update_step(step, level="ERROR", status_message=type(exc).__name__)

        raise

    finally:
        end_step(step)
