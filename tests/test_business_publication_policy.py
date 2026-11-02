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


def test_structured_provider_identity_is_not_rejected_for_a_generic_sounding_name() -> None:
    now = utcnow()
    result = BusinessValidationService(None)._business_type(
        SimpleNamespace(
            id="business_1",
            display_name="Home Electrical Services",
            is_directory=False,
            phone="4165550101",
            domain=None,
        ),
        SimpleNamespace(
            id="source_1",
            source_observation_id="observation_1",
            provider_id="google_places",
            external_id="places/home-electrical-services",
            title="Home Electrical Services",
            source_url="https://maps.google.com/example",
        ),
        now,
        now,
    )

    assert result.status == "passed"
    assert result.evidence[0]["structured_provider_identity"] is True


def test_observation_validation_accepts_structured_google_display_name() -> None:
    now = utcnow()
    results = BusinessValidationService(None).evaluate_observation(
        business=SimpleNamespace(
            id="business_1",
            display_name="CertaPro Painters of North York",
            phone="6479335628",
            domain="certapro.com",
            website_url="https://certapro.com/north-york/",
            is_directory=False,
            address="4789 Yonge St, North York, ON",
            geography="North York, ON",
            latitude=43.76,
            longitude=-79.41,
        ),
        observation=SimpleNamespace(
            id="observation_1",
            source="google_places",
            external_id="places/certapro-north-york",
            source_url="https://certapro.com/north-york/",
            observed_at=now,
            raw_payload={
                "displayName": {"text": "CertaPro Painters of North York"},
                "primaryTypeDisplayName": "Painter",
                "types": ["painter"],
                "formattedAddress": "4789 Yonge St, North York, ON",
            },
        ),
        segment=SimpleNamespace(
            niche_id="niche_1",
            market_key="north-york",
            market_label="North York",
            niche=SimpleNamespace(
                slug="home_service_painting",
                label="Painting",
                category="painting contractor",
                search_config={},
            ),
        ),
    )

    business_identity = next(
        result for result in results if result.validation_type == "business_identity"
    )
    assert business_identity.status == "passed"
    assert business_identity.evidence[0]["title"] == "certapro painters of north york"


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
