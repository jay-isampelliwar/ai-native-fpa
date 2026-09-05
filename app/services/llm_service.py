"""The only place in the backend where a language model is constructed.

Skills, nodes and tools ask this module for a model rather than instantiating one, so
provider, model name, temperature, timeout and retry policy are decided once. Swapping
providers or pinning a new model version is then a change here, not a search across
every skill folder.

There are two models rather than one because the two jobs have opposite requirements.
The router does classification: it must be cheap, fast and boring, so it runs at
temperature zero on a small model and its answer is a single skill name. The explanation
model writes to a human about their own money, so it gets the larger model - but still
at low temperature, because it is narrating verified numbers it was handed and any
creativity there is a fabricated financial figure.

``max_retries`` is deliberately low. A retry storm against a paid API during an incident
costs real money and delays the user's error message; bounded retries with a hard
timeout fail fast and let the graph record the failure.

Both constructors are cached, so one client with one connection pool is shared across
requests instead of being rebuilt per graph run.
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import settings


@lru_cache
def get_router_model() -> ChatOpenAI:

    """Build the cheap deterministic model used only to classify a request into a skill name."""

    return ChatOpenAI(
        model=settings.router_model,
        api_key=settings.openai_api_key.get_secret_value(),
        temperature=0.0,
        timeout=float(settings.absolute_timeout_seconds),
        max_retries=2,
    )


@lru_cache
def get_explanation_model() -> ChatOpenAI:

    """Build the model that narrates already verified numbers back to the user, never one that computes them."""

    return ChatOpenAI(
        model=settings.explanation_model,
        api_key=settings.openai_api_key.get_secret_value(),
        temperature=0.2,
        timeout=float(settings.absolute_timeout_seconds),
        max_retries=2,
    )
