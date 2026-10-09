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
    DEV_USER_ID: int = 1


@lru_cache
def get_settings() -> Settings:

    """Build the settings once and reuse them for every caller."""

    return Settings()
