from app.config import Settings
from campaigns.schemas import CampaignCreate
import pytest
from pydantic import ValidationError

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


def test_settings_accepts_multiple_apify_sources(monkeypatch) -> None:
    monkeypatch.setenv("APIFY_API_TOKEN", "global-token")
    monkeypatch.setenv(
        "APIFY_SOURCES",
        (
            '[{"id":"kijiji","label":"Kijiji","actor_id":"owner/kijiji"},'
            '{"id":"homestars","label":"HomeStars","actor_id":"owner/homestars",'
            '"input_template":{"search":"{{query}}","maxResults":"{{limit}}"}}]'
        ),
    )

    settings = Settings()
    sources = settings.apify_source_configs

    assert [source["id"] for source in sources] == ["kijiji", "homestars"]
    assert sources[0]["api_token"] == "global-token"
    assert sources[1]["label"] == "HomeStars"
    assert sources[1]["input_template"] == {"search": "{{query}}", "maxResults": "{{limit}}"}


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


def test_database_url_rejects_sqlite_runtime_urls() -> None:
    with pytest.raises(DatabaseConfigurationError, match="Postgres URL"):
        normalize_database_url("sqlite:///./data/soutlead.db")


def test_campaign_create_requires_explicit_setup_fields() -> None:
    with pytest.raises(ValidationError):
        CampaignCreate(product_id="product_123")
