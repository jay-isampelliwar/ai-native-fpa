"""Typed application settings, read once from the environment at import time.

Every value the backend needs to reach the outside world lives here and nowhere else.
Modules import ``settings`` rather than calling ``os.environ``, so a missing or
malformed variable fails loudly at startup instead of halfway through a user's
retirement projection.

Secrets are typed as ``SecretStr`` on purpose: pydantic then refuses to print them in
logs, tracebacks and ``repr`` output. That matters more than usual here because our
structured logs and LangSmith traces are shipped off box, and an API key that leaks into
a trace is a key that has to be rotated.

``checkpoint_encryption_key`` is separate from every other secret because it protects
data at rest in the LangGraph checkpoint table. Rotating it is a migration, not a
redeploy, so it is deliberately not defaulted - the application must refuse to start
rather than silently write unencrypted state.

Model budgets live here too. They are the ceiling a skill definition may not exceed, so
a mistake in one skill's metadata cannot run up an unbounded bill.
"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    """All environment driven configuration, validated once so startup fails fast on a bad value."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    debug: bool = False

    database_url: SecretStr
    checkpoint_encryption_key: SecretStr

    openai_api_key: SecretStr
    router_model: str = "gpt-4o-mini"
    explanation_model: str = "gpt-4o"

    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "ai-native-fpa"
    tracing_enabled: bool = False

    default_timezone: str = "Asia/Kolkata"
    default_currency: str = "INR"

    absolute_maximum_model_calls: int = Field(default=8, ge=1)
    absolute_maximum_tool_calls: int = Field(default=16, ge=1)
    absolute_timeout_seconds: int = Field(default=60, ge=1)

    approval_expiry_seconds: int = Field(default=900, ge=60)


@lru_cache
def get_settings() -> Settings:

    """Build and cache the settings object so the environment is parsed exactly once per process."""

    return Settings()


settings = get_settings()
