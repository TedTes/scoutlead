from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from canonical.website_evidence import (
    assess_website_ownership,
    trusted_website_evidence,
)
from canonical.repository import CanonicalRepository
from db.models import BusinessModel, ValidationResultModel
from db.session import create_database


def test_no_candidate_url_does_not_create_ownership_validation() -> None:
    assert (
        assess_website_ownership(
            source="google_places",
            payload={"displayName": {"text": "North Star Painting"}},
            business_name="North Star Painting",
            business_phone=None,
        )
        is None
    )


def test_structured_listing_requires_business_identity_evidence() -> None:
    assessment = assess_website_ownership(
        source="google_places",
        payload={
            "displayName": {"text": "Unrelated Garden Centre"},
            "websiteUri": "https://unrelated-garden.example",
        },
        business_name="North Star Painting",
        business_phone=None,
    )

    assert assessment is not None
    assert assessment.status == "uncertain"
    assert assessment.confidence < 90
    assert (
        trusted_website_evidence(
            source="google_places",
            payload={
                "displayName": {"text": "Unrelated Garden Centre"},
                "websiteUri": "https://unrelated-garden.example",
            },
            business_name="North Star Painting",
            business_phone=None,
        )
        is None
    )


def test_matching_structured_listing_passes_website_ownership() -> None:
    assessment = assess_website_ownership(
        source="google_places",
        payload={
            "displayName": {"text": "North Star Painting"},
            "websiteUri": "https://northstarpainting.example",
        },
        business_name="North Star Painting",
        business_phone=None,
    )

    assert assessment is not None
    assert assessment.status == "passed"
    assert assessment.confidence >= 90


def test_kijiji_url_is_rejected_as_official_website_evidence() -> None:
    assessment = assess_website_ownership(
        source="google_places",
        payload={
            "displayName": {"text": "North Star Painting"},
            "websiteUri": "https://www.kijiji.ca/v-services/north-star-painting/123",
        },
        business_name="North Star Painting",
        business_phone=None,
    )

    assert assessment is not None
    assert assessment.status == "failed"
    assert assessment.confidence == 100
    assert "marketplace" in assessment.reason.lower()


def test_failed_enrichment_identity_rejects_only_the_website_claim() -> None:
    assessment = assess_website_ownership(
        source="company_website_seed",
        payload={
            "website_url": "https://different-company.example",
            "website_enrichment": {
                "availability_status": "active",
                "inspected_urls": ["https://different-company.example"],
                "phones": ["647-555-0199"],
            },
        },
        business_name="North Star Painting",
        business_phone="416-555-0101",
    )

    assert assessment is not None
    assert assessment.status == "failed"
    assert "identity" in assessment.reason.lower()


def test_canonical_ingest_records_ownership_and_does_not_promote_uncertain_url() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        link = CanonicalRepository(session).upsert_from_discovery_result(
            company_name="North Star Painting",
            website_url="https://unrelated-garden.example",
            geography="Toronto",
            source="google_places",
            raw={
                "id": "places/north-star",
                "displayName": {"text": "Unrelated Garden Centre"},
                "websiteUri": "https://unrelated-garden.example",
            },
        )

        business = session.get(BusinessModel, link.business_id)
        validation = session.scalar(
            select(ValidationResultModel).where(
                ValidationResultModel.business_id == link.business_id,
                ValidationResultModel.validation_type == "website_ownership",
            )
        )

        assert business is not None
        assert business.website_url is None
        assert business.domain is None
        assert validation is not None
        assert validation.status == "uncertain"
        assert validation.confidence < 90
