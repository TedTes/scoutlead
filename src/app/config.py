from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "soutlead"
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/soutlead.db"
    port: int = 8000

    search_api_endpoint: str | None = None
    search_api_key: str | None = None

    llm_json_endpoint: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None

    email_provider_endpoint: str | None = None
    email_api_key: str | None = None

    request_timeout_seconds: float = Field(default=20.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
