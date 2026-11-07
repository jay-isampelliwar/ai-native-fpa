"""The Langfuse client and its LangChain callback handler, built from the app settings."""

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app.core.config import Settings


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


def shutdown_langfuse(settings: Settings) -> None:

    """Send every trace still waiting in the queue and stop the client, so nothing is lost when a process exits."""

    client = create_langfuse(settings)

    if client is None:
        return

    client.shutdown()
