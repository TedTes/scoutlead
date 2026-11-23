from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class WebsiteAssessmentLabel(StrEnum):
    STRONG = "strong"
    ACCEPTABLE = "acceptable"
    UPGRADE_CANDIDATE = "upgrade_candidate"
    BROKEN = "broken"


@dataclass(frozen=True)
class WebsiteAssessmentFeatures:
    business_id: str
    website_url: str | None
    values: dict[str, float | None]
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WebsiteAssessmentPrediction:
    label: WebsiteAssessmentLabel
    upgrade_probability: float
    confidence: float
    reasons: list[str]
    model_key: str
    model_version: str
    feature_coverage: float

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["label"] = self.label.value
        return payload


class WebsiteAssessmentModel(Protocol):
    key: str
    version: str

    def predict(
        self, features: WebsiteAssessmentFeatures
    ) -> WebsiteAssessmentPrediction: ...
