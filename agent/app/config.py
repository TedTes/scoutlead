from functools import lru_cache
import json
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "soutlead"
    environment: Literal["local", "dev", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    database_url: str = ""
    port: int = 8000
    auto_create_tables: bool = True
    api_auth_token: str | None = None
    cors_origins: str | list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    search_api_endpoint: str | None = None
    search_api_key: str | None = None
    search_provider: Literal["generic", "tavily", "brave"] = "generic"
    google_places_api_key: str | None = None
    google_places_api_endpoint: str | None = None

    allow_mock_providers: bool = False
    require_real_search: bool = False
    require_real_email: bool = False
    require_real_llm: bool = False

    llm_json_endpoint: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    email_provider: Literal["console", "http", "resend"] = "console"
    email_provider_endpoint: str | None = None
    email_api_key: str | None = None
    resend_api_key: str | None = None
    email_from_address: str | None = None
    email_from_name: str = "Soutlead"
    email_reply_to: str | None = None

    request_timeout_seconds: float = Field(default=20.0, gt=0)

    @property
    def strict_external_providers(self) -> bool:
        return self.environment in {"staging", "production"} and not self.allow_mock_providers

    @field_validator("cors_origins", mode="after")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            raw_value = value.strip()
            if raw_value.startswith("["):
                parsed = json.loads(raw_value)
                if not isinstance(parsed, list):
                    raise ValueError("CORS_ORIGINS JSON value must be a list")
                return [str(origin).strip() for origin in parsed if str(origin).strip()]
            return [origin.strip() for origin in raw_value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
