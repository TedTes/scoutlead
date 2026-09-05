from functools import lru_cache
import json
import os
from pathlib import Path
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApifySourceSettings(BaseModel):
    id: str = Field(min_length=1)
    label: str | None = None
    enabled: bool = True
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

    app_name: str = "ScoutLead"
    environment: Literal["local", "dev", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    database_url: str = ""
    port: int = 8000
    auto_create_tables: bool = True
    api_auth_token: str | None = None
    cors_origins: str | list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    require_user_auth: bool = False
    clerk_secret_key: str | None = None
    clerk_jwt_issuer: str | None = None
    clerk_jwks_url: str | None = None

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
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = Field(default=1536, gt=0, le=4096)
    semantic_cache_min_score: float = Field(default=0.78, ge=0, le=1)
    semantic_cache_min_results: int = Field(default=5, ge=0, le=100)

    email_provider: Literal["console", "http", "resend", "gmail"] = "console"
    email_provider_endpoint: str | None = None
    email_api_key: str | None = None
    resend_api_key: str | None = None
    email_from_address: str | None = None
    email_from_name: str = "ScoutLead"
    email_reply_to: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str | None = None
    google_oauth_state_secret: str | None = None
    google_oauth_auth_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_oauth_token_url: str = "https://oauth2.googleapis.com/token"
    google_userinfo_url: str = "https://openidconnect.googleapis.com/v1/userinfo"
    google_token_encryption_key: str | None = None
    gmail_api_base_url: str = "https://gmail.googleapis.com/gmail/v1"
    gmail_oauth_scopes: list[str] = [
        "openid",
        "email",
        "https://www.googleapis.com/auth/gmail.send",
    ]

    contact_verification_provider: Literal["syntax", "http", "bouncer", "zerobounce"] = "syntax"
    email_verification_endpoint: str | None = None
    email_verification_api_key: str | None = None
    bouncer_api_key: str | None = None
    bouncer_api_endpoint: str | None = None
    zerobounce_api_key: str | None = None
    zerobounce_api_endpoint: str | None = None

    request_timeout_seconds: float = Field(default=20.0, gt=0)

    @property
    def strict_external_providers(self) -> bool:
        return self.environment in {"staging", "production"} and not self.allow_mock_providers

    @property
    def apify_source_configs(self) -> list[dict[str, Any]]:
        parsed_sources = self._parse_apify_source_envs() or self._parse_apify_sources()
        if parsed_sources:
            return [
                source
                for source in (self._normalize_apify_source(source) for source in parsed_sources)
                if source["enabled"]
            ]

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
            "enabled": parsed.enabled,
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

    def _parse_apify_source_envs(self) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        for env_name, raw_value in sorted(_merged_env_values().items()):
            if not _is_apify_source_env(env_name):
                continue
            source_id = _source_id_from_env_name(env_name)
            parsed = _json_object_env(raw_value, env_name)
            configured_id = str(
                parsed.get("id")
                or parsed.get("provider_id")
                or parsed.get("source_provider_id")
                or source_id
            ).strip()
            if not _same_source_id(configured_id, source_id):
                raise ValueError(
                    f"{env_name} config id '{configured_id}' does not match source '{source_id}'"
                )
            parsed["id"] = configured_id or source_id
            sources.append(parsed)
        return sources

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


_APIFY_SOURCE_ENV_PREFIX = "APIFY_SOURCE_"
_RESERVED_APIFY_SOURCE_ENV_NAMES = {
    "APIFY_SOURCE_PROVIDER_ID",
    "APIFY_SOURCE_LABEL",
}


def _is_apify_source_env(env_name: str) -> bool:
    return (
        env_name.startswith(_APIFY_SOURCE_ENV_PREFIX)
        and env_name not in _RESERVED_APIFY_SOURCE_ENV_NAMES
        and len(env_name) > len(_APIFY_SOURCE_ENV_PREFIX)
    )


def _source_id_from_env_name(env_name: str) -> str:
    suffix = env_name[len(_APIFY_SOURCE_ENV_PREFIX) :]
    normalized = re.sub(r"[^a-z0-9_]+", "_", suffix.lower()).strip("_")
    normalized = re.sub(r"_+", "_", normalized)
    if not normalized:
        raise ValueError(f"{env_name} is missing a source id suffix")
    return normalized


def _same_source_id(configured_id: str, env_source_id: str) -> bool:
    compact_configured = re.sub(r"[^a-z0-9]+", "", configured_id.lower())
    compact_env = re.sub(r"[^a-z0-9]+", "", env_source_id.lower())
    return compact_configured == compact_env


def _json_object_env(raw_value: str, env_name: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{env_name} must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{env_name} must be a JSON object")
    return dict(parsed)


def _merged_env_values() -> dict[str, str]:
    values = _dotenv_values(Path(".env"))
    values.update(os.environ)
    return values


def _dotenv_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values
