from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from business_attributes.repository import attribute_value
from db.models import BusinessAttributeModel, BusinessModel
from website_assessments.contracts import WebsiteAssessmentFeatures


FEATURE_KEYS = (
    "website_missing",
    "website_unreachable",
    "website_quality_gap",
    "performance_gap",
    "accessibility_gap",
    "best_practices_gap",
    "seo_gap",
    "mobile_performance_gap",
    "mobile_viewport_gap",
    "mobile_overflow_gap",
    "small_tap_targets_gap",
    "broken_images_gap",
    "content_structure_gap",
)

SCORE_FEATURES = {
    "website_quality_gap": "website_quality_score",
    "performance_gap": "performance_score",
    "accessibility_gap": "accessibility_score",
    "best_practices_gap": "best_practices_score",
    "seo_gap": "seo_score",
    "mobile_performance_gap": "mobile_performance_score",
}


def extract_website_features(
    business: BusinessModel,
    attributes: dict[str, BusinessAttributeModel],
    *,
    now: datetime | None = None,
) -> WebsiteAssessmentFeatures:
    now = now or datetime.now(timezone.utc)
    website_fact = attributes.get("website_url")
    website_value = attribute_value(website_fact)
    website_url = str(business.website_url or website_value or "").strip() or None
    status_fact = attributes.get("website_status")
    status = str(attribute_value(status_fact) or "").strip().lower()

    values: dict[str, float | None] = {key: None for key in FEATURE_KEYS}
    evidence: dict[str, dict[str, Any]] = {}

    if status in {"missing", "unavailable"}:
        values["website_missing"] = 1.0
        evidence["website_missing"] = _evidence(status_fact, now)
    elif website_url or status in {"present", "available", "thin", "parked", "unreachable"}:
        values["website_missing"] = 0.0
        if status_fact is not None:
            evidence["website_missing"] = _evidence(status_fact, now)

    if status:
        values["website_unreachable"] = 1.0 if status in {"unreachable", "parked"} else 0.0
        evidence["website_unreachable"] = _evidence(status_fact, now)

    for feature_key, attribute_key in SCORE_FEATURES.items():
        fact = attributes.get(attribute_key)
        numeric = _number(attribute_value(fact))
        if numeric is None:
            continue
        values[feature_key] = 1.0 - max(0.0, min(100.0, numeric)) / 100.0
        evidence[feature_key] = _evidence(fact, now)

    viewport_fact = attributes.get("mobile_viewport_present")
    viewport = attribute_value(viewport_fact)
    if isinstance(viewport, bool):
        values["mobile_viewport_gap"] = 0.0 if viewport else 1.0
        evidence["mobile_viewport_gap"] = _evidence(viewport_fact, now)

    capture_fact = attributes.get("website_visual_capture")
    capture = attribute_value(capture_fact)
    if isinstance(capture, dict):
        metrics = capture.get("page_metrics")
        if isinstance(metrics, dict):
            overflow = _number(metrics.get("mobile_horizontal_overflow_px"))
            if overflow is not None:
                values["mobile_overflow_gap"] = min(1.0, max(0.0, overflow) / 120.0)
                evidence["mobile_overflow_gap"] = _evidence(capture_fact, now)
            tap_ratio = _number(metrics.get("mobile_small_tap_target_ratio"))
            if tap_ratio is not None:
                values["small_tap_targets_gap"] = min(1.0, max(0.0, tap_ratio))
                evidence["small_tap_targets_gap"] = _evidence(capture_fact, now)
            broken_images = _number(metrics.get("broken_image_count"))
            if broken_images is not None:
                values["broken_images_gap"] = min(1.0, max(0.0, broken_images) / 3.0)
                evidence["broken_images_gap"] = _evidence(capture_fact, now)
            heading_count = _number(metrics.get("heading_count"))
            word_count = _number(metrics.get("word_count"))
            if heading_count is not None and word_count is not None:
                values["content_structure_gap"] = (
                    1.0 if word_count >= 150 and heading_count == 0 else 0.0
                )
                evidence["content_structure_gap"] = _evidence(capture_fact, now)

    return WebsiteAssessmentFeatures(
        business_id=business.id,
        website_url=website_url,
        values=values,
        evidence=evidence,
    )


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _evidence(
    fact: BusinessAttributeModel | None,
    now: datetime,
) -> dict[str, Any]:
    if fact is None:
        return {}
    expires_at = fact.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return {
        "attribute_key": fact.attribute_key,
        "confidence": int(fact.confidence or 0),
        "fresh": expires_at is None or expires_at >= now,
        "observed_at": fact.observed_at.isoformat(),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "source_provider": fact.source_provider,
        "source_url": fact.source_url,
    }
