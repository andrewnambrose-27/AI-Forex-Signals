import pytest

from app.core.config import Settings


def test_cors_origins_accepts_single_render_url():
    settings = Settings(jwt_secret_key="test-secret", cors_origins="https://signals.27tools.co")

    assert settings.cors_origin_list == ["https://signals.27tools.co"]


def test_cors_origins_accepts_comma_separated_urls():
    settings = Settings(
        jwt_secret_key="test-secret",
        cors_origins="https://signals.27tools.co, http://localhost:3000",
    )

    assert settings.cors_origin_list == ["https://signals.27tools.co", "http://localhost:3000"]


def test_cors_origins_accepts_json_list_string():
    settings = Settings(
        jwt_secret_key="test-secret",
        cors_origins='["https://signals.27tools.co", "http://localhost:3000"]',
    )

    assert settings.cors_origin_list == ["https://signals.27tools.co", "http://localhost:3000"]


def test_database_url_accepts_render_postgresql_scheme():
    settings = Settings(
        jwt_secret_key="test-secret",
        database_url="postgresql://user:password@render-host:5432/database",
    )

    assert settings.effective_database_url == "postgresql+psycopg://user:password@render-host:5432/database"


def test_render_rejects_local_docker_database_hostname():
    settings = Settings(
        jwt_secret_key="test-secret",
        environment="render",
        database_url="postgresql+psycopg://postgres:postgres@db:5432/forex_signals",
    )

    with pytest.raises(RuntimeError, match="Docker Compose host 'db'"):
        settings.validate_runtime_configuration()
