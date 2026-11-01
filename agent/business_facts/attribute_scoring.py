from __future__ import annotations

from dataclasses import dataclass
from math import log1p
from typing import Any, Mapping


SCORE_VERSION = 1
UNKNOWN_TEXT_VALUES = frozenset({"", "unknown", "not_checked", "not_verified"})


@dataclass(frozen=True)
class AttributeScore:
    """The observed condition of one business attribute.

    `score` describes the digital footprint (0=poor/gap, 100=strong).
    It deliberately does not describe whether the evidence is trustworthy;
    evidence confidence remains on `business_facts.confidence`.
    """

    score: float | None
    reason: str
    version: int = SCORE_VERSION


BOOLEAN_POSITIVE_ATTRIBUTES = frozenset(
    {
        "business_operational",
        "uses_https",
        "mobile_viewport_present",
        "contact_form_present",
        "quote_or_booking_form_present",
        "primary_cta_present",
        "click_to_call_present",
        "public_email_present",
        "public_phone_present",
        "google_business_profile_present",
        "local_business_schema_present",
        "service_area_content_present",
        "service_area_pages_present",
        "title_and_meta_present",
        "complete_contact_details",
        "online_payment_or_financing_present",
        "testimonials_present",
        "privacy_policy_present",
        "html_language_present",
        "hreflang_present",
        "language_selector_present",
        "market_language_supported",
    }
)

BOOLEAN_NEGATIVE_ATTRIBUTES = frozenset(
    {
        "is_directory",
        "is_chain",
        "is_franchise",
    }
)

PRESENCE_ATTRIBUTES = frozenset(
    {
        "business_name",
        "trade_category",
        "provider_business_id",
        "address",
        "city",
        "region",
        "postal_code",
        "latitude",
        "longitude",
        "phone",
        "website_url",
        "domain",
        "contact_page_url",
        "booking_url",
        "contact_form_url",
        "verified_email",
        "verified_phone",
        "preferred_contact_channel",
    }
)

DIRECT_SCORE_ATTRIBUTES = frozenset(
    {
        "website_quality_score",
        "mobile_performance_score",
        "performance_score",
        "accessibility_score",
        "best_practices_score",
        "seo_score",
    }
)


def score_attribute(
    key: str,
    value: Any,
    *,
    opportunity_direction: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> AttributeScore:
    """Normalize one observed attribute onto a 0-100 footprint scale.

    Unknown is always returned as ``None`` rather than zero. Definition
    configuration can override the built-in mapping with ``score_values`` or
    explicit numeric ``score_min``/``score_max`` bounds.
    """

    config = config or {}
    if _unknown(value):
        return AttributeScore(None, "unknown values are not scored")

    configured = config.get("score_values")
    if isinstance(configured, Mapping):
        normalized = _normalized_key(value)
        configured_value = configured.get(normalized)
        if isinstance(configured_value, (int, float)):
            return AttributeScore(_clamp(configured_value), f"configured value: {normalized}")

    if key in BOOLEAN_POSITIVE_ATTRIBUTES or opportunity_direction == "false_is_opportunity":
        if isinstance(value, bool):
            return AttributeScore(100.0 if value else 0.0, "present" if value else "missing")
    if key in BOOLEAN_NEGATIVE_ATTRIBUTES and isinstance(value, bool):
        return AttributeScore(0.0 if value else 100.0, "excluded classification" if value else "independent business")
    if opportunity_direction == "true_is_opportunity" and isinstance(value, bool):
        return AttributeScore(0.0 if value else 100.0, "undesired state present" if value else "desired state")

    if key in PRESENCE_ATTRIBUTES:
        return AttributeScore(100.0, "observed value is present")

    if key == "website_status":
        return _categorical(
            value,
            {
                "present": 100,
                "available": 100,
                "thin": 45,
                "unreachable": 25,
                "parked": 10,
                "unavailable": 0,
                "missing": 0,
                # A listing gap is not proof that no website exists. Keep it
                # visible as weak coverage without letting it qualify as a
                # verified website-absence opportunity (default cutoff < 50).
                "not_listed": 55,
            },
        )
    if key == "website_ownership":
        return _categorical(value, {"passed": 100, "uncertain": 50, "failed": 0})
    if key == "http_status":
        try:
            status = int(float(value))
        except (TypeError, ValueError):
            return AttributeScore(None, "HTTP status is not numeric")
        if 200 <= status < 300:
            return AttributeScore(100.0, "successful HTTP response")
        if 300 <= status < 400:
            return AttributeScore(75.0, "redirecting HTTP response")
        if 400 <= status < 500:
            return AttributeScore(20.0, "client-error HTTP response")
        if status >= 500:
            return AttributeScore(0.0, "server-error HTTP response")
        return AttributeScore(None, "unsupported HTTP status")
    if key in DIRECT_SCORE_ATTRIBUTES:
        return _numeric(value, 0.0, 100.0, higher_is_better=True)
    if key == "google_rating":
        return _numeric(value, 1.0, 5.0, higher_is_better=True)
    if key == "google_review_count":
        try:
            count = max(0.0, float(value))
        except (TypeError, ValueError):
            return AttributeScore(None, "review count is not numeric")
        # Smooth growth: 0→0, 15→46, 50→66, 250→90, 500+→100.
        return AttributeScore(_clamp(100 * log1p(count) / log1p(500)), "log-scaled review count")
    if key == "review_recency_days":
        return _numeric(value, 0.0, float(config.get("score_max") or 365), higher_is_better=False)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = config.get("score_min")
        maximum = config.get("score_max")
        if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)):
            return _numeric(
                value,
                float(minimum),
                float(maximum),
                higher_is_better=opportunity_direction != "higher_is_opportunity",
            )
        threshold = config.get("opportunity_threshold")
        if isinstance(threshold, (int, float)):
            if opportunity_direction == "lower_is_opportunity":
                return _numeric(value, 0.0, max(float(threshold) * 2, 1.0), higher_is_better=True)
            if opportunity_direction == "higher_is_opportunity":
                return _numeric(value, 0.0, max(float(threshold) * 2, 1.0), higher_is_better=False)

    if isinstance(value, bool):
        return AttributeScore(100.0 if value else 0.0, "boolean state")
    return AttributeScore(None, "no scoring rule for this attribute")


def is_opportunity_score(score: float | None, *, maximum_score: float = 49.999) -> bool:
    return score is not None and score <= maximum_score


def _unknown(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and value.strip().lower() in UNKNOWN_TEXT_VALUES
    )


def _categorical(value: Any, values: Mapping[str, float]) -> AttributeScore:
    normalized = _normalized_key(value)
    score = values.get(normalized)
    if score is None:
        return AttributeScore(None, f"unmapped categorical value: {normalized}")
    return AttributeScore(float(score), f"mapped categorical value: {normalized}")


def _numeric(value: Any, minimum: float, maximum: float, *, higher_is_better: bool) -> AttributeScore:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return AttributeScore(None, "value is not numeric")
    if maximum <= minimum:
        return AttributeScore(None, "invalid scoring bounds")
    score = 100 * (number - minimum) / (maximum - minimum)
    if not higher_is_better:
        score = 100 - score
    return AttributeScore(_clamp(score), "normalized numeric value")


def _normalized_key(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_")


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 2)
