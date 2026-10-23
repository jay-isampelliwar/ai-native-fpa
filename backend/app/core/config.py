"""Settings read from the environment and the .env file."""

from functools import lru_cache

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
    MEMORY_MODEL: str = "gpt-4o-mini"

    TURN_TIMEOUT_SECONDS: float = 90
    TOOL_TIMEOUT_SECONDS: float = 10
    TOOL_RETRY_ATTEMPTS: int = 3
    TOOL_RETRY_BASE_SECONDS: float = 0.5
    MIN_RETRY_SECONDS: float = 2
    DB_STATEMENT_TIMEOUT_MS: int = 8000
    DB_CONNECT_TIMEOUT_SECONDS: int = 5


@lru_cache
def get_settings() -> Settings:

    """Build the settings once and reuse them for every caller."""

    return Settings()
