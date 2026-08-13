from app.config import Settings
import pytest

from db.session import DatabaseConfigurationError, normalize_database_url


def test_settings_accepts_comma_separated_cors_origins(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://web.example.com, https://admin.example.com")

    settings = Settings()

    assert settings.cors_origins == ["https://web.example.com", "https://admin.example.com"]


def test_settings_accepts_json_cors_origins(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["https://web.example.com"]')

    settings = Settings()

    assert settings.cors_origins == ["https://web.example.com"]


def test_settings_accepts_dev_environment(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "dev")

    settings = Settings()

    assert settings.environment == "dev"


def test_database_url_normalizes_railway_postgres_url() -> None:
    assert (
        normalize_database_url("postgresql://user:pass@host:5432/db")
        == "postgresql+psycopg://user:pass@host:5432/db"
    )


def test_database_url_rejects_empty_value() -> None:
    with pytest.raises(DatabaseConfigurationError, match="DATABASE_URL is empty"):
        normalize_database_url("")


def test_database_url_rejects_unresolved_railway_reference() -> None:
    with pytest.raises(DatabaseConfigurationError, match="unresolved variable reference"):
        normalize_database_url("${{postgres.DATABASE_URL}}")
