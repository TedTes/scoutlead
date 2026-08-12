from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "soutlead"
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/soutlead.db"
    port: int = 8000
    auto_create_tables: bool = True
    api_auth_token: str | None = None
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    search_api_endpoint: str | None = None
    search_api_key: str | None = None
    search_provider: Literal["generic", "tavily", "brave"] = "generic"

    llm_json_endpoint: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    email_provider_endpoint: str | None = None
    email_api_key: str | None = None

    request_timeout_seconds: float = Field(default=20.0, gt=0)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
