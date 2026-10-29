"""Settings read from the environment and the .env file."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    """Values the app needs at runtime, loaded once from env or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        )

    OPENAI_API_KEY: SecretStr
    CHAT_MODEL: str = "gpt-4o-mini"
    DATABASE_URL: str | None = None
    JWT_SECRET: SecretStr
    TOKEN_TTL_MINUTES: int = 60 * 24 * 7
    COOKIE_SECURE: bool = False

    REDIS_URL: str
    REDIS_MEMORY_STREAM: str = "ai-native-fpa:memory"
    REDIS_MEMORY_CONSUMER_GROUP: str = "memory-workers"
    REDIS_MEMORY_CONSUMER_NAME: str = "memory-worker-1"
    MEMORY_WORKER_BATCH_SIZE: int = 10
    MEMORY_WORKER_RETRY_LIMIT: int = 5
    MEMORY_WORKER_CLAIM_AFTER_SECONDS: int = 300
    REDIS_RUN_STREAM: str = "ai-native-fpa:runs"
    REDIS_RUN_CONSUMER_GROUP: str = "agent-workers"
    REDIS_RUN_CHANNEL_PREFIX: str = "ai-native-fpa:run"
    RUN_EXECUTION: Literal["inline", "queue"] = "inline"
    RUN_WORKER_CONCURRENCY: int = 8
    RUN_MAX_ATTEMPTS: int = 3
    RUN_HEARTBEAT_SECONDS: int = 10
    RUN_STALE_AFTER_SECONDS: int = 60
    RUN_RESEND_AFTER_SECONDS: int = 30
    RUN_CLAIM_AFTER_SECONDS: int = 30
    RUN_EVENTS_KEEP_HOURS: int = 24
    MEMORY_MODEL: str = "gpt-4o-mini"
    INTENT_MODEL: str = "gpt-4o-mini"
    INTENT_TIMEOUT_SECONDS: float = 5

    TURN_TIMEOUT_SECONDS: float = 90
    TOOL_TIMEOUT_SECONDS: float = 10
    TOOL_RETRY_ATTEMPTS: int = 3
    TOOL_RETRY_BASE_SECONDS: float = 0.5
    MIN_RETRY_SECONDS: float = 2
    DB_STATEMENT_TIMEOUT_MS: int = 8000
    DB_CONNECT_TIMEOUT_SECONDS: int = 5

    MAX_MODEL_CALLS: int = 12
    MAX_TOOL_CALLS: int = 20
    MAX_OUTPUT_TOKENS_PER_CALL: int = 2000
    MAX_OUTPUT_TOKENS_PER_TURN: int = 12000
    WRAP_UP_MAX_TOKENS: int = 300
    GRAPH_RECURSION_LIMIT: int = 80
    MODEL_PRICES_USD_PER_MILLION: dict[str, tuple[float, float]] = {"gpt-4o-mini": (0.15, 0.60)}


@lru_cache
def get_settings() -> Settings:

    """Build the settings once and reuse them for every caller."""

    return Settings()
