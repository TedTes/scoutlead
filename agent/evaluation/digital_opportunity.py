from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from products.schemas import ProductRead


OPPORTUNITY_LEVEL_RANK = {
    "none": 0,
    "low": 1,
    "moderate": 2,
    "high": 3,
}

OPPORTUNITY_PROBLEM_PHRASES = (
    "weak website",
    "outdated website",
    "missing website",
    "no website",
    "missing quote",
    "no quote",
    "missing booking",
    "no booking",
    "weak conversion",
    "poor conversion",
    "low review",
    "poor review",
    "local reputation",
    "digital opportunity",
)


@dataclass(frozen=True)
class OpportunitySignal:
    key: str
    message: str
    points: int
    source_url: str | None = None
    value: str | int | float | bool | None = None


@dataclass(frozen=True)
class DigitalOpportunityAssessment:
    score: int
    level: str
    signals: tuple[OpportunitySignal, ...]
    version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "score": self.score,
            "level": self.level,
            "signals": [asdict(signal) for signal in self.signals],
        }


def assess_digital_opportunity(
    *,
    website_reachable: bool,
    uses_https: bool | None,
    has_mobile_viewport: bool | None,
    has_quote_or_booking_form: bool | None,
    rating: float | None,
    review_count: int | None,
    website_source_url: str | None,
    reviews_source_url: str | None,
) -> DigitalOpportunityAssessment:
    signals: list[OpportunitySignal] = []

    if not website_reachable:
        signals.append(
            OpportunitySignal(
                key="website_unreachable",
                message="Website could not be loaded.",
                points=45,
                source_url=website_source_url,
            )
        )
    else:
        if uses_https is False:
            signals.append(
                OpportunitySignal(
                    key="missing_https",
                    message="Website does not use HTTPS.",
                    points=15,
                    source_url=website_source_url,
                )
            )
        if has_mobile_viewport is False:
            signals.append(
                OpportunitySignal(
                    key="missing_mobile_viewport",
                    message="Website is missing a mobile viewport declaration.",
                    points=15,
                    source_url=website_source_url,
                )
            )
        if has_quote_or_booking_form is False:
            signals.append(
                OpportunitySignal(
                    key="missing_quote_or_booking_form",
                    message="No quote, estimate, or booking form was found on inspected pages.",
                    points=30,
                    source_url=website_source_url,
                )
            )

    if rating is not None and rating < 4.3:
        signals.append(
            OpportunitySignal(
                key="low_google_rating",
                message=f"Google rating is {rating:g}.",
                points=20,
                source_url=reviews_source_url,
                value=rating,
            )
        )
    if review_count is not None and review_count < 20:
        signals.append(
            OpportunitySignal(
                key="low_google_review_count",
                message=f"Google profile has {review_count} reviews.",
                points=15,
                source_url=reviews_source_url,
                value=review_count,
            )
        )

    score = min(100, sum(signal.points for signal in signals))
    if score >= 50:
        level = "high"
    elif score >= 25:
        level = "moderate"
    elif score > 0:
        level = "low"
    else:
        level = "none"
    return DigitalOpportunityAssessment(score=score, level=level, signals=tuple(signals))


def opportunity_evidence_from_sources(
    sources: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the latest versioned digital-opportunity observation in lead evidence."""
    candidates: list[tuple[int, dict[str, Any]]] = []
    for source in sources:
        for key, value in _walk_items(source):
            if key == "digital_opportunity" and isinstance(value, dict):
                level = str(value.get("level") or "").strip().lower()
                if level in OPPORTUNITY_LEVEL_RANK:
                    candidates.append((len(candidates), value))
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda candidate: (
            str(candidate[1].get("assessed_at") or ""),
            _safe_int(candidate[1].get("version")),
            candidate[0],
        ),
    )[1]


def has_minimum_opportunity(
    sources: list[dict[str, Any]],
    *,
    minimum: str = "moderate",
) -> bool:
    evidence = opportunity_evidence_from_sources(sources)
    if evidence is None:
        return False
    required = OPPORTUNITY_LEVEL_RANK.get(minimum.lower())
    if required is None:
        raise ValueError(f"unknown opportunity level: {minimum}")
    actual = OPPORTUNITY_LEVEL_RANK[str(evidence.get("level") or "none").lower()]
    return actual >= required


def opportunity_score_from_sources(sources: list[dict[str, Any]]) -> int:
    evidence = opportunity_evidence_from_sources(sources)
    return _safe_int(evidence.get("score")) if evidence else 0


def product_requires_digital_opportunity(product: ProductRead) -> bool:
    """Identify products whose buyers want businesses with fixable digital gaps."""
    text = " ".join(
        value
        for value in [
            product.product_description,
            product.problem_being_solved,
            product.value_proposition,
            product.offer_summary,
            *product.ideal_customer_signals,
        ]
        if value
    ).lower()
    return any(phrase in text for phrase in OPPORTUNITY_PROBLEM_PHRASES)


def _walk_items(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk_items(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_items(item)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
