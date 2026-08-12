from app.config import Settings


def test_settings_accepts_comma_separated_cors_origins(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://web.example.com, https://admin.example.com")

    settings = Settings()

    assert settings.cors_origins == ["https://web.example.com", "https://admin.example.com"]


def test_settings_accepts_json_cors_origins(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["https://web.example.com"]')

    settings = Settings()

    assert settings.cors_origins == ["https://web.example.com"]
