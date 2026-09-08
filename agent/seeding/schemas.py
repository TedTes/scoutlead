from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.utils import normalize_text


OperatorType = Literal["solo", "small_team", "business", "unknown"]


class BusinessSeedInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    company_name: str = Field(min_length=1)
    website_url: str | None = None
    phone: str | None = None
    contact_email: str | None = None
    contact_name: str | None = None
    contact_role: str | None = None
    geography: str | None = None
    address: str | None = None
    description: str | None = None
    source: str = "manual_seed"
    source_url: str | None = None
    external_id: str | None = None
    query: str | None = None
    signals: list[str] = Field(default_factory=list)
    seed_niche: str = "home_service_painting"
    seed_market: str | None = None
    operator_type: OperatorType = "unknown"
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "company_name",
        "website_url",
        "phone",
        "contact_email",
        "contact_name",
        "contact_role",
        "geography",
        "address",
        "description",
        "source",
        "source_url",
        "external_id",
        "query",
        "seed_niche",
        "seed_market",
        mode="before",
    )
    @classmethod
    def clean_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = normalize_text(value)
            return cleaned or None
        return value

    @field_validator("source", "seed_niche", mode="after")
    @classmethod
    def default_required_text(cls, value: str | None, info) -> str:
        if value:
            return value
        if info.field_name == "source":
            return "manual_seed"
        return "home_service_painting"

    @field_validator("signals", mode="before")
    @classmethod
    def parse_signals(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [normalize_text(item) for item in value.split(",") if normalize_text(item)]
        if isinstance(value, list):
            return [normalize_text(str(item)) for item in value if normalize_text(str(item))]
        return []


class BusinessSeedRowError(BaseModel):
    row_number: int
    message: str


class BusinessSeedImportSummary(BaseModel):
    batch_id: str
    dry_run: bool = False
    rows_read: int = 0
    rows_valid: int = 0
    businesses_created: int = 0
    businesses_updated: int = 0
    contacts_created: int = 0
    source_observations_created: int = 0
    skipped_rows: int = 0
    errors: list[BusinessSeedRowError] = Field(default_factory=list)

