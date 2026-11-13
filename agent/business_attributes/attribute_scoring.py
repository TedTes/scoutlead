from __future__ import annotations

from dataclasses import dataclass
from math import log1p
from typing import Any, Mapping


SCORE_VERSION = 2
UNKNOWN_TEXT_VALUES = frozenset({"", "unknown", "not_checked", "not_verified"})


@dataclass(frozen=True)
class AttributeScore:
    """The lead opportunity represented by one observed business attribute.

    `score` uses one direction everywhere: 0=no opportunity, 100=strong opportunity.
    It deliberately does not describe whether the evidence is trustworthy;
    evidence confidence remains on `business_attributes.confidence`.
    """

    score: float | None
    reason: str
    version: int = SCORE_VERSION


BOOLEAN_POSITIVE_ATTRIBUTES = frozenset(
    {
        "business_operational",
        "mobile_viewport_present",
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
    """Normalize one observed attribute onto a 0-100 opportunity scale.

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
            return AttributeScore(
                0.0 if value else 100.0,
                "no opportunity: present" if value else "strong opportunity: missing",
            )
    if key in BOOLEAN_NEGATIVE_ATTRIBUTES and isinstance(value, bool):
        return AttributeScore(
            100.0 if value else 0.0,
            "undesired classification present" if value else "excluded classification absent",
        )
    if opportunity_direction == "true_is_opportunity" and isinstance(value, bool):
        return AttributeScore(
            100.0 if value else 0.0,
            "opportunity state present" if value else "opportunity state absent",
        )

    if key in PRESENCE_ATTRIBUTES:
        return AttributeScore(0.0, "observed value does not represent an opportunity")

    if key == "website_status":
        return _categorical(
            value,
            {
                "present": 0,
                "available": 0,
                "thin": 55,
                "unreachable": 75,
                "parked": 90,
                "unavailable": 100,
                "missing": 100,
            },
        )
    if key == "website_ownership":
        return AttributeScore(0.0, "ownership is evidence context, not an opportunity")
    if key == "http_status":
        try:
            status = int(float(value))
        except (TypeError, ValueError):
            return AttributeScore(None, "HTTP status is not numeric")
        if 200 <= status < 300:
            return AttributeScore(0.0, "successful HTTP response")
        if 300 <= status < 400:
            return AttributeScore(25.0, "redirecting HTTP response")
        if 400 <= status < 500:
            return AttributeScore(80.0, "client-error HTTP response")
        if status >= 500:
            return AttributeScore(100.0, "server-error HTTP response")
        return AttributeScore(None, "unsupported HTTP status")
    if key in DIRECT_SCORE_ATTRIBUTES:
        return _numeric(value, 0.0, 100.0, higher_is_opportunity=False)
    if key == "google_rating":
        return _numeric(value, 1.0, 5.0, higher_is_opportunity=False)
    if key == "google_review_count":
        try:
            count = max(0.0, float(value))
        except (TypeError, ValueError):
            return AttributeScore(None, "review count is not numeric")
        # Smooth opportunity decay: 0→100, 15→54, 50→34, 250→10, 500+→0.
        return AttributeScore(
            _clamp(100 - 100 * log1p(count) / log1p(500)),
            "inverse log-scaled review count",
        )
    if key == "review_recency_days":
        return _numeric(
            value,
            0.0,
            float(config.get("score_max") or 365),
            higher_is_opportunity=True,
        )
    if key == "domain_age_days":
        # Domain age is supporting footprint context, not proof of business
        # quality. Cap the gradual strength score at ten years.
        return AttributeScore(0.0, "domain age is evidence context, not an opportunity")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = config.get("score_min")
        maximum = config.get("score_max")
        if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)):
            return _numeric(
                value,
                float(minimum),
                float(maximum),
                higher_is_opportunity=opportunity_direction == "higher_is_opportunity",
            )
        threshold = config.get("opportunity_threshold")
        if isinstance(threshold, (int, float)):
            if opportunity_direction == "lower_is_opportunity":
                return _numeric(
                    value,
                    0.0,
                    max(float(threshold) * 2, 1.0),
                    higher_is_opportunity=False,
                )
            if opportunity_direction == "higher_is_opportunity":
                return _numeric(
                    value,
                    0.0,
                    max(float(threshold) * 2, 1.0),
                    higher_is_opportunity=True,
                )

    if isinstance(value, bool):
        return AttributeScore(0.0, "boolean evidence has no opportunity rule")
    if opportunity_direction == "none":
        return AttributeScore(0.0, "observed value has no opportunity rule")
    return AttributeScore(None, "no scoring rule for this attribute")


def is_opportunity_score(score: float | None, *, minimum_score: float = 50.001) -> bool:
    return score is not None and score >= minimum_score


def audience_match_config(
    key: str,
    opportunity_direction: str,
    config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return the opportunity-score cutoff used by audience matching."""

    result = dict(config or {})
    if isinstance(result.get("audience_min_score"), (int, float)):
        return result
    legacy_maximum = result.pop("audience_max_score", None)
    if isinstance(legacy_maximum, (int, float)):
        result["audience_min_score"] = round(100.0 - float(legacy_maximum), 3)
        return result
    threshold = result.get("opportunity_threshold")
    if opportunity_direction in {"lower_is_opportunity", "higher_is_opportunity"} and isinstance(
        threshold, (int, float)
    ):
        normalized = score_attribute(
            key,
            threshold,
            opportunity_direction=opportunity_direction,
            config=result,
        ).score
        if normalized is not None:
            result["audience_min_score"] = min(100.0, normalized + 0.001)
    return result


def _unknown(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and value.strip().lower() in UNKNOWN_TEXT_VALUES
    )


def _categorical(value: Any, values: Mapping[str, float]) -> AttributeScore:
    normalized = _normalized_key(value)
    if normalized == "not_listed":
        return AttributeScore(None, "listing has no website, but absence is not verified")
    score = values.get(normalized)
    if score is None:
        return AttributeScore(None, f"unmapped categorical value: {normalized}")
    return AttributeScore(float(score), f"mapped categorical value: {normalized}")


def _numeric(
    value: Any,
    minimum: float,
    maximum: float,
    *,
    higher_is_opportunity: bool,
) -> AttributeScore:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return AttributeScore(None, "value is not numeric")
    if maximum <= minimum:
        return AttributeScore(None, "invalid scoring bounds")
    score = 100 * (number - minimum) / (maximum - minimum)
    if not higher_is_opportunity:
        score = 100 - score
    return AttributeScore(_clamp(score), "normalized opportunity severity")


def _normalized_key(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_")


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 2)
