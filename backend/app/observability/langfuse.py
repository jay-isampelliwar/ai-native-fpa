"""The Langfuse client, its LangChain callback handler and the trace attributes of a turn, built from the app settings."""

from contextlib import AbstractContextManager, nullcontext
from typing import Any

from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

from app.core.config import Settings


TRACE_NAME = "preeti-financial-planner"
TRACE_TAGS = ["preeti", "financial-planner"]


def langfuse_enabled(settings: Settings) -> bool:

    """True when both Langfuse keys are set, so traces have somewhere to go."""

    return bool(settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY)


def create_langfuse(settings: Settings) -> Langfuse | None:

    """Build the Langfuse client from the settings, or None when its keys are missing."""

    if not langfuse_enabled(settings):
        return None

    return Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY.get_secret_value(),
        base_url=settings.LANGFUSE_BASE_URL,
        )


def langfuse_handler(settings: Settings) -> CallbackHandler | None:

    """A LangChain callback handler that sends each model and tool call to Langfuse, or None when tracing is off."""

    if create_langfuse(settings) is None:
        return None

    return CallbackHandler(public_key=settings.LANGFUSE_PUBLIC_KEY)


def tracing_context(
    settings: Settings,
    user_id: int,
    conversation_id: int,
    run_id: int,
    worker_id: str,
    ) -> AbstractContextManager[Any]:

    """Give every span made inside it the turn's user, conversation as session, trace name, tags and run, or do nothing when tracing is off."""

    if not langfuse_enabled(settings):
        return nullcontext()

    return propagate_attributes(
        user_id=str(user_id),
        session_id=str(conversation_id),
        trace_name=TRACE_NAME,
        tags=TRACE_TAGS,
        metadata={"run_id": str(run_id), "worker_id": worker_id},
        )


def shutdown_langfuse(settings: Settings) -> None:

    """Send every trace still waiting in the queue and stop the client, so nothing is lost when a process exits."""

    client = create_langfuse(settings)

    if client is None:
        return

    client.shutdown()
