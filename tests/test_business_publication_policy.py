from types import SimpleNamespace

from business_validation.policy import publication_decision
from business_validation.validation import BusinessValidationService, _is_generic_business_title
from shared.utils import utcnow
from niches.catalog import NICHE_BY_SLUG, NICHE_CATALOG
from seeding.google_places import NICHE_INCLUDED_TYPES, NICHE_QUERY_TEMPLATES


def _result(validation_type: str, status: str = "passed", confidence: int = 95):
    return SimpleNamespace(
        validation_type=validation_type,
        status=status,
        confidence=confidence,
        reason=f"{validation_type} is {status}",
    )


def test_publication_requires_every_validation_dimension() -> None:
    decision = publication_decision(
        [_result("identity"), _result("business_identity"), _result("trade")]
    )

    assert decision.status == "needs_review"
    assert decision.missing == ("location",)


def test_failed_validation_rejects_publication() -> None:
    decision = publication_decision(
        [
            _result("identity"),
            _result("business_identity", status="failed"),
            _result("trade"),
            _result("location"),
        ]
    )

    assert decision.status == "rejected"
    assert decision.publishable is False


def test_complete_high_confidence_validation_is_publishable() -> None:
    decision = publication_decision(
        [
            _result("identity"),
            _result("business_identity"),
            _result("trade"),
            _result("location"),
        ]
    )

    assert decision.publishable is True


def test_all_profile_niches_have_google_source_definitions() -> None:
    assert set(NICHE_BY_SLUG) == set(NICHE_QUERY_TEMPLATES)
    assert set(NICHE_BY_SLUG) == set(NICHE_INCLUDED_TYPES)
    assert {"cleaners", "landscapers", "pest_control", "garage_doors"} <= set(
        NICHE_CATALOG
    )


def test_generic_search_headlines_are_not_business_identities() -> None:
    assert _is_generic_business_title("find painters in toronto") is True
    assert _is_generic_business_title("professional painter for hire") is True
    assert _is_generic_business_title(
        "best 15 house painters painting companies in toronto on"
    ) is True
    assert _is_generic_business_title("the best 10 roofing near toronto on canada") is True
    assert _is_generic_business_title("best roofing company in toronto r askto") is True
    assert _is_generic_business_title(
        "69 ads for garage door repair in services in toronto gta kijiji marketplaces"
    ) is True
    assert _is_generic_business_title("cedar ridge painting") is False


def test_configured_search_is_verification_only_not_business_identity() -> None:
    now = utcnow()
    result = BusinessValidationService(None)._business_type(
        SimpleNamespace(id="business_1", display_name="Cedar Ridge Painting", is_directory=False),
        SimpleNamespace(
            id="source_1",
            source_observation_id="observation_1",
            provider_id="configured_search",
            title="Cedar Ridge Painting",
            source_url="https://cedarridge.example",
        ),
        now,
        now,
    )

    assert result.status == "failed"
    assert result.evidence[0]["verification_only_provider"] is True


def test_secondary_provider_category_does_not_override_primary_trade() -> None:
    now = utcnow()
    result = BusinessValidationService(None)._trade(
        SimpleNamespace(id="business_1"),
        SimpleNamespace(
            id="source_1",
            source_observation_id="observation_1",
            title="No More Chores Toronto",
            raw_payload={
                "raw": {
                    "primaryTypeDisplayName": "House cleaning service",
                    "types": ["cleaning_service", "laundry"],
                }
            },
        ),
        SimpleNamespace(
            niche_id="niche_1",
            market_key="toronto",
            niche=SimpleNamespace(
                slug="home_service_cleaning",
                label="Residential cleaning services",
                category="residential cleaning services",
            ),
        ),
        now,
        now,
    )

    assert result.status == "passed"
    assert result.evidence[0]["excluded_terms"] == ["laundry"]
    assert result.evidence[0]["decisive_excluded_terms"] == []


def test_excluded_trade_in_business_title_remains_a_failure() -> None:
    now = utcnow()
    result = BusinessValidationService(None)._trade(
        SimpleNamespace(id="business_1"),
        SimpleNamespace(
            id="source_1",
            source_observation_id="observation_1",
            title="Trendy Laundromat and Dry Cleaners",
            raw_payload={"raw": {"types": ["cleaning_service"]}},
        ),
        SimpleNamespace(
            niche_id="niche_1",
            market_key="toronto",
            niche=SimpleNamespace(
                slug="home_service_cleaning",
                label="Residential cleaning services",
                category="residential cleaning services",
            ),
        ),
        now,
        now,
    )

    assert result.status == "failed"
    assert "dry clean" in result.evidence[0]["decisive_excluded_terms"]
