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
