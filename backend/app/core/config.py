from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Forex Signals"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    database_url: str = "postgresql+psycopg://postgres:postgres@db:5432/forex_signals"
    redis_url: str | None = "redis://redis:6379/0"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    market_data_api_key: str | None = None
    news_api_key: str | None = None

    ig_environment: str = "DEMO"
    ig_api_key: str | None = None
    ig_username: str | None = None
    ig_password: str | None = None
    ig_account_id: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
