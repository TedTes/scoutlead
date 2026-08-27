from functools import lru_cache
import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApifySourceSettings(BaseModel):
    id: str = Field(min_length=1)
    label: str | None = None
    actor_id: str | None = None
    api_token: str | None = None
    api_base_url: str | None = None
    input_kind: str | None = None
    search_url_template: str | None = None
    category_slug: str | None = None
    location_code: str | None = None
    input_template: str | dict[str, Any] | None = None
    result_mapping: str | dict[str, Any] | None = None
    max_charge_usd: float | None = Field(default=None, ge=0)
    detail: str | None = None


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
    apify_api_token: str | None = None
    apify_api_base_url: str = "https://api.apify.com/v2"
    apify_sources: str | None = None
    apify_source_provider_id: str = "apify_actor"
    apify_source_label: str = "Kijiji"
    apify_actor_id: str | None = None
    apify_actor_input_template: str | None = None
    apify_actor_result_mapping: str | None = None
    apify_actor_max_charge_usd: float | None = Field(default=None, ge=0)

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

    @property
    def apify_source_configs(self) -> list[dict[str, Any]]:
        parsed_sources = self._parse_apify_sources()
        if parsed_sources:
            return [self._normalize_apify_source(source) for source in parsed_sources]

        if not self.apify_source_provider_id:
            return []

        return [
            self._normalize_apify_source(
                {
                    "id": self.apify_source_provider_id,
                    "label": self.apify_source_label,
                    "actor_id": self.apify_actor_id,
                    "api_token": self.apify_api_token,
                    "api_base_url": self.apify_api_base_url,
                    "input_template": self.apify_actor_input_template,
                    "result_mapping": self.apify_actor_result_mapping,
                    "max_charge_usd": self.apify_actor_max_charge_usd,
                    "detail": f"{self.apify_source_label} listings",
                }
            )
        ]

    def _parse_apify_sources(self) -> list[dict[str, Any]]:
        if not self.apify_sources:
            return []
        parsed = json.loads(self.apify_sources)
        if not isinstance(parsed, list):
            raise ValueError("APIFY_SOURCES must be a JSON array")
        return [dict(item) for item in parsed if isinstance(item, dict)]

    def _normalize_apify_source(self, source: dict[str, Any]) -> dict[str, Any]:
        data = dict(source)
        if "id" not in data:
            data["id"] = data.get("provider_id") or data.get("source_provider_id")
        parsed = ApifySourceSettings.model_validate(data)
        label = parsed.label or parsed.id
        return {
            "id": parsed.id,
            "label": label,
            "actor_id": parsed.actor_id,
            "api_token": parsed.api_token or self.apify_api_token,
            "api_base_url": parsed.api_base_url or self.apify_api_base_url,
            "input_kind": parsed.input_kind,
            "search_url_template": parsed.search_url_template,
            "category_slug": parsed.category_slug,
            "location_code": parsed.location_code,
            "input_template": parsed.input_template,
            "result_mapping": parsed.result_mapping,
            "max_charge_usd": parsed.max_charge_usd,
            "detail": parsed.detail or f"{label} listings",
        }

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
