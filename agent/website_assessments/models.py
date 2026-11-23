from __future__ import annotations

import json
from dataclasses import dataclass
from math import exp
from pathlib import Path
from typing import Any

from website_assessments.contracts import (
    WebsiteAssessmentFeatures,
    WebsiteAssessmentLabel,
    WebsiteAssessmentPrediction,
)


DEFAULT_COEFFICIENTS = {
    "website_missing": 4.5,
    "website_unreachable": 2.2,
    "website_quality_gap": 2.4,
    "performance_gap": 1.5,
    "accessibility_gap": 0.8,
    "best_practices_gap": 0.8,
    "seo_gap": 0.7,
    "mobile_performance_gap": 1.2,
    "mobile_viewport_gap": 0.8,
    "mobile_overflow_gap": 1.4,
    "small_tap_targets_gap": 0.7,
    "broken_images_gap": 1.0,
    "content_structure_gap": 0.6,
}

REASON_LABELS = {
    "website_missing": "No business website was found",
    "website_unreachable": "The stored website could not be reached",
    "website_quality_gap": "The measured website-quality score is low",
    "performance_gap": "The measured performance score is low",
    "accessibility_gap": "The measured accessibility score is low",
    "best_practices_gap": "The measured best-practices score is low",
    "seo_gap": "The measured SEO score is low",
    "mobile_performance_gap": "The measured mobile performance score is low",
    "mobile_viewport_gap": "The site is missing a mobile viewport declaration",
    "mobile_overflow_gap": "The mobile page has horizontal layout overflow",
    "small_tap_targets_gap": "Many mobile controls are difficult to tap",
    "broken_images_gap": "The captured page contains broken images",
    "content_structure_gap": "The page has substantial text without clear headings",
}


@dataclass(frozen=True)
class LinearWebsiteAssessmentModel:
    """Small, replaceable baseline operating on the stable feature contract."""

    key: str = "linear_website_baseline"
    version: str = "baseline-1"
    intercept: float = -1.25
    coefficients: dict[str, float] | None = None

    def predict(
        self, features: WebsiteAssessmentFeatures
    ) -> WebsiteAssessmentPrediction:
        coefficients = self.coefficients or DEFAULT_COEFFICIENTS
        observed = {
            key: value
            for key, value in features.values.items()
            if value is not None and key in coefficients
        }
        evidence_quality = [
            _evidence_quality(features.evidence.get(key, {})) for key in observed
        ]
        coverage = len(observed) / max(1, len(coefficients))
        confidence = (
            sum(evidence_quality) / len(evidence_quality) * min(1.0, coverage * 2.5)
            if evidence_quality
            else 0.0
        )
        logit = self.intercept + sum(
            coefficients[key] * float(value) * _evidence_quality(features.evidence.get(key, {}))
            for key, value in observed.items()
        )
        probability = 1.0 / (1.0 + exp(-max(-30.0, min(30.0, logit))))
        if observed.get("website_missing") == 1.0:
            probability = max(probability, 0.98)
        label = _label(probability)
        contributions = sorted(
            (
                coefficients[key]
                * float(value)
                * _evidence_quality(features.evidence.get(key, {})),
                key,
            )
            for key, value in observed.items()
            if float(value) > 0
        )
        reasons = [REASON_LABELS[key] for _, key in reversed(contributions[-3:])]
        if not reasons:
            reasons = [
                "The available measurements do not show a strong website-upgrade signal"
                if observed
                else "Website quality has not been measured yet"
            ]
        return WebsiteAssessmentPrediction(
            label=label,
            upgrade_probability=round(probability, 4),
            confidence=round(confidence, 4),
            reasons=reasons,
            model_key=self.key,
            model_version=self.version,
            feature_coverage=round(coverage, 4),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "LinearWebsiteAssessmentModel":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            key=str(payload.get("model_key") or "linear_website_baseline"),
            version=str(payload["model_version"]),
            intercept=float(payload["intercept"]),
            coefficients={
                str(key): float(value)
                for key, value in dict(payload["coefficients"]).items()
            },
        )


def _evidence_quality(evidence: dict[str, Any]) -> float:
    if not evidence:
        return 0.65
    confidence = max(0.0, min(100.0, float(evidence.get("confidence") or 0.0))) / 100.0
    freshness = 1.0 if evidence.get("fresh", True) else 0.5
    return confidence * freshness


def _label(probability: float) -> WebsiteAssessmentLabel:
    if probability >= 0.82:
        return WebsiteAssessmentLabel.BROKEN
    if probability >= 0.55:
        return WebsiteAssessmentLabel.UPGRADE_CANDIDATE
    if probability >= 0.28:
        return WebsiteAssessmentLabel.ACCEPTABLE
    return WebsiteAssessmentLabel.STRONG
