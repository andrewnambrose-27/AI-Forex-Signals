from functools import lru_cache
import json
import os
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Forex Signals"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000"

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

    @property
    def cors_origin_list(self) -> list[str]:
        value = self.cors_origins
        if not value:
            return ["http://localhost:3000"]

        stripped = value.strip()
        if stripped.startswith("["):
            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                raise ValueError("CORS_ORIGINS JSON value must be a list")
            return [str(origin).strip() for origin in parsed if str(origin).strip()]

        return [origin.strip() for origin in stripped.split(",") if origin.strip()]

    @property
    def is_render(self) -> bool:
        return self.environment.lower() == "render" or bool(os.getenv("RENDER"))

    @property
    def effective_database_url(self) -> str:
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url

    def validate_runtime_configuration(self) -> None:
        parsed_database_url = urlparse(self.effective_database_url)
        if self.is_render and parsed_database_url.hostname == "db":
            raise RuntimeError(
                "DATABASE_URL points to Docker Compose host 'db'. "
                "On Render, set DATABASE_URL to the Render PostgreSQL Internal Database URL."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
