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


def test_settings_accepts_gmail_email_provider(monkeypatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail")

    settings = Settings()

    assert settings.email_provider == "gmail"
    assert settings.gmail_oauth_scopes == [
        "openid",
        "email",
        "https://www.googleapis.com/auth/gmail.send",
    ]


def test_settings_accepts_multiple_apify_sources(monkeypatch) -> None:
    monkeypatch.setenv("APIFY_API_TOKEN", "global-token")
    monkeypatch.setenv(
        "APIFY_SOURCE_KIJIJI",
        (
            '{"id":"kijiji","label":"Kijiji","actor_id":"owner/kijiji",'
            '"input_template":{"search":"{{query}}","maxResults":"{{limit}}"}}'
        ),
    )
    monkeypatch.setenv(
        "APIFY_SOURCE_HOMESTARS",
        (
            '{"id":"homestars","label":"HomeStars","actor_id":"owner/homestars",'
            '"input_kind":"text_query","search_url_template":"https://example.test/{{query_slug}}",'
            '"input_template":{"search":"{{query}}","maxResults":"{{limit}}"}}'
        ),
    )

    settings = Settings()
    sources = settings.apify_source_configs
    sources_by_id = {source["id"]: source for source in sources}

    assert sorted(source["id"] for source in sources) == ["homestars", "kijiji"]
    assert sources_by_id["kijiji"]["api_token"] == "global-token"
    assert sources_by_id["homestars"]["label"] == "HomeStars"
    assert sources_by_id["homestars"]["input_kind"] == "text_query"
    assert (
        sources_by_id["homestars"]["search_url_template"]
        == "https://example.test/{{query_slug}}"
    )
    assert sources_by_id["homestars"]["input_template"] == {
        "search": "{{query}}",
        "maxResults": "{{limit}}",
    }


def test_settings_derives_apify_source_id_from_env_name(monkeypatch) -> None:
    monkeypatch.setenv("APIFY_API_TOKEN", "global-token")
    monkeypatch.setenv(
        "APIFY_SOURCE_KIJIJI",
        '{"label":"Kijiji","actor_id":"owner/kijiji","input_template":{"query":"{{query}}"}}',
    )

    sources = Settings().apify_source_configs

    assert len(sources) == 1
    assert sources[0]["id"] == "kijiji"
    assert sources[0]["label"] == "Kijiji"


def test_settings_rejects_apify_source_id_that_does_not_match_env_name(monkeypatch) -> None:
    monkeypatch.setenv("APIFY_SOURCE_KIJIJI", '{"id":"homestars","actor_id":"owner/source"}')

    with pytest.raises(ValueError, match="does not match source 'kijiji'"):
        Settings().apify_source_configs


def test_settings_skips_disabled_apify_source_env(monkeypatch) -> None:
    monkeypatch.setenv("APIFY_SOURCE_KIJIJI", '{"id":"kijiji","enabled":false}')

    assert Settings().apify_source_configs == []


def test_settings_keeps_legacy_apify_sources_when_no_per_source_env_exists(monkeypatch) -> None:
    monkeypatch.setenv("APIFY_API_TOKEN", "global-token")
    monkeypatch.setenv(
        "APIFY_SOURCES",
        (
            '[{"id":"kijiji","label":"Kijiji","actor_id":"owner/kijiji",'
            '"input_template":{"search":"{{query}}","maxResults":"{{limit}}"}}]'
        ),
    )

    sources = Settings().apify_source_configs

    assert [source["id"] for source in sources] == ["kijiji"]


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
