from evaluation.digital_opportunity import (
    assess_digital_opportunity,
    has_minimum_opportunity,
    opportunity_evidence_from_sources,
    opportunity_score_from_sources,
    product_requires_digital_opportunity,
    source_inputs_require_digital_opportunity,
)
from products.schemas import ProductRead, QualificationCriterion
from datetime import UTC, datetime


def test_assessment_scores_only_observed_opportunities() -> None:
    assessment = assess_digital_opportunity(
        website_reachable=True,
        uses_https=False,
        has_mobile_viewport=False,
        has_quote_or_booking_form=False,
        rating=4.1,
        review_count=8,
        website_source_url="http://painter.example",
        reviews_source_url="https://maps.example/painter",
    )

    assert assessment.score == 95
    assert assessment.level == "high"
    assert {signal.key for signal in assessment.signals} == {
        "missing_https",
        "missing_mobile_viewport",
        "missing_quote_or_booking_form",
        "low_google_rating",
        "low_google_review_count",
    }


def test_assessment_does_not_penalize_unknown_review_data() -> None:
    assessment = assess_digital_opportunity(
        website_reachable=True,
        uses_https=True,
        has_mobile_viewport=True,
        has_quote_or_booking_form=True,
        rating=None,
        review_count=None,
        website_source_url="https://painter.example",
        reviews_source_url=None,
    )

    assert assessment.score == 0
    assert assessment.level == "none"
    assert assessment.signals == ()


def test_nested_versioned_opportunity_evidence_is_extracted() -> None:
    sources = [
        {"digital_opportunity": {"version": 1, "score": 15, "level": "low"}},
        {
            "raw": {
                "digital_opportunity": {
                    "version": 2,
                    "score": 55,
                    "level": "high",
                    "signals": [{"key": "website_unreachable"}],
                }
            }
        },
    ]

    assert opportunity_evidence_from_sources(sources)["version"] == 2
    assert opportunity_score_from_sources(sources) == 55
    assert has_minimum_opportunity(sources, minimum="moderate") is True


def test_missing_or_low_opportunity_does_not_meet_delivery_threshold() -> None:
    assert has_minimum_opportunity([], minimum="moderate") is False
    assert has_minimum_opportunity(
        [{"digital_opportunity": {"version": 1, "score": 15, "level": "low"}}],
        minimum="moderate",
    ) is False


def test_latest_assessment_replaces_stale_stronger_assessment() -> None:
    sources = [
        {
            "digital_opportunity": {
                "version": 1,
                "assessed_at": "2026-09-01T00:00:00+00:00",
                "score": 80,
                "level": "high",
            }
        },
        {
            "raw": {
                "digital_opportunity": {
                    "version": 1,
                    "assessed_at": "2026-09-29T00:00:00+00:00",
                    "score": 15,
                    "level": "low",
                }
            }
        },
    ]

    assert opportunity_score_from_sources(sources) == 15
    assert has_minimum_opportunity(sources, minimum="moderate") is False


def test_web_growth_product_requires_digital_opportunity() -> None:
    now = datetime.now(UTC)
    product = ProductRead(
        id="product_web_growth",
        product_name="Local Service Website Growth",
        product_description="Website and conversion improvements for local businesses.",
        target_customer="Independent home-service businesses",
        problem_being_solved="Weak websites and missing quote or booking flows.",
        value_proposition="Generate more qualified inquiries.",
        target_geography="Toronto",
        validation_goal="Find sales opportunities.",
        qualification_criteria=[QualificationCriterion(label="Local service business")],
        ideal_customer_signals=["Low review count"],
        created_at=now,
        updated_at=now,
    )

    assert product_requires_digital_opportunity(product) is True


def test_saved_search_prompt_can_require_digital_opportunity() -> None:
    assert source_inputs_require_digital_opportunity(
        {
            "source_request_prompt": (
                "Independent painters in Toronto with weak or outdated websites "
                "or no visible quote form."
            )
        }
    ) is True
