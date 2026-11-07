"""The Langfuse client, its LangChain callback handler and the trace attributes of a turn, built from the app settings, never failing the caller."""

import logging
from contextlib import AbstractContextManager, nullcontext
from typing import Any

from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

from app.core.config import Settings


log = logging.getLogger(__name__)

TRACE_NAME = "preeti-financial-planner"
TRACE_TAGS = ["preeti", "financial-planner"]


def langfuse_enabled(settings: Settings) -> bool:

    """True when both Langfuse keys are set, so traces have somewhere to go."""

    return bool(settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY)


def create_langfuse(settings: Settings) -> Langfuse | None:

    """Build the Langfuse client from the settings, or None when its keys are missing or it fails to start."""

    if not langfuse_enabled(settings):
        return None

    try:
        return Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY.get_secret_value(),
            base_url=settings.LANGFUSE_BASE_URL,
            )

    except Exception:

        log.exception("Langfuse client failed to start, so tracing is off")

        return None


def langfuse_handler(settings: Settings) -> CallbackHandler | None:

    """A LangChain callback handler that sends each model and tool call to Langfuse, or None when tracing is off or it fails to build."""

    if create_langfuse(settings) is None:
        return None

    try:
        return CallbackHandler(public_key=settings.LANGFUSE_PUBLIC_KEY)

    except Exception:

        log.exception("Langfuse callback handler failed to build, so this turn is not traced")

        return None


def tracing_context(
    settings: Settings,
    user_id: int,
    conversation_id: int,
    run_id: int,
    worker_id: str,
    ) -> AbstractContextManager[Any]:

    """Give every span made inside it the turn's user, conversation as session, trace name, tags and run, or do nothing when tracing is off or fails."""

    if not langfuse_enabled(settings):
        return nullcontext()

    try:
        return propagate_attributes(
            user_id=str(user_id),
            session_id=str(conversation_id),
            trace_name=TRACE_NAME,
            tags=TRACE_TAGS,
            metadata={"run_id": str(run_id), "worker_id": worker_id},
            )

    except Exception:

        log.exception("Langfuse trace attributes failed to build, so this turn has none")

        return nullcontext()


def shutdown_langfuse(settings: Settings) -> None:

    """Send every trace still waiting in the queue and stop the client, logging instead of raising if that fails."""

    client = create_langfuse(settings)

    if client is None:
        return

    try:
        client.shutdown()

    except Exception:
        log.exception("Langfuse shutdown failed, so some traces may be lost")
