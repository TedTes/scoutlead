import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from canonical.repository import CanonicalRepository
from db.models import (
    BusinessModel,
    BusinessNicheMembershipModel,
    CampaignModel,
    ContactModel,
    LeadModel,
    NicheModel,
    SeedBatchModel,
    SourceObservationModel,
)
from db.session import create_database
from seeding.schemas import BusinessSeedInput
from seeding.service import BusinessSeedService


class FakeEmbeddingClient:
    model = "fake-embedding"
    dimension = 6

    def embed_text(self, text: str) -> list[float]:
        lower = text.lower()
        return [
            sum(lower.count(term) for term in ("paint", "painter", "painting")),
            sum(lower.count(term) for term in ("toronto", "gta", "ontario")),
            sum(lower.count(term) for term in ("quote", "estimate")),
            sum(lower.count(term) for term in ("owner", "solo")),
            sum(lower.count(term) for term in ("hvac", "roof", "plumb")),
            1.0,
        ]


def test_business_seed_import_populates_canonical_and_niche_tables() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        summary = BusinessSeedService(session).import_seeds([painting_seed()], batch_id="painting-toronto-v1")

        assert summary.rows_read == 1
        assert summary.rows_valid == 1
        assert summary.businesses_created == 1
        assert summary.businesses_updated == 0
        assert summary.contacts_created == 1
        assert summary.source_observations_created == 1
        assert _count(session, BusinessModel) == 1
        assert _count(session, ContactModel) == 1
        assert _count(session, SourceObservationModel) == 1
        assert _count(session, NicheModel) == 1
        assert _count(session, SeedBatchModel) == 1
        assert _count(session, BusinessNicheMembershipModel) == 1
        assert _count(session, LeadModel) == 0
        assert _count(session, CampaignModel) == 0

        business = session.scalar(select(BusinessModel))
        assert business is not None
        assert business.display_name == "Example Solo Painting Co."
        assert business.domain == "example-solo-painting.test"
        assert business.phone == "4165550101"
        contact = session.scalar(select(ContactModel))
        assert contact is not None
        assert contact.business_id == business.id
        assert contact.email == "owner@example-solo-painting.test"
        assert contact.phone == "4165550101"
        assert contact.name == "Alex Painter"
        assert contact.role == "Owner/Operator"

        observation = session.scalar(select(SourceObservationModel))
        assert observation is not None
        assert observation.business_id == business.id
        assert observation.source == "manual_seed"
        assert observation.external_id
        assert observation.raw_payload["seed_batch_id"] == "painting-toronto-v1"
        assert observation.raw_payload["seed_niche"] == "home_service_painting"
        assert observation.raw_payload["operator_type"] == "solo"

        niche = session.scalar(select(NicheModel))
        assert niche is not None
        assert niche.slug == "home_service_painting"
        assert niche.label == "Home Service Painting"
        assert niche.default_query == "solo residential painters in Toronto with estimate forms"

        seed_batch = session.scalar(select(SeedBatchModel))
        assert seed_batch is not None
        assert seed_batch.id == "painting-toronto-v1"
        assert seed_batch.niche_id == niche.id
        assert seed_batch.market_key == "toronto gta"
        assert seed_batch.status == "completed"
        assert seed_batch.found_count == 1
        assert seed_batch.inserted_count == 1
        assert seed_batch.updated_count == 0
        assert seed_batch.source_observation_count == 1

        membership = session.scalar(select(BusinessNicheMembershipModel))
        assert membership is not None
        assert membership.business_id == business.id
        assert membership.niche_id == niche.id
        assert membership.seed_batch_id == seed_batch.id
        assert membership.source_observation_id == observation.id
        assert membership.market_key == "toronto gta"
        assert membership.confidence == 1.0
        assert membership.evidence[0]["type"] == "seed_import"
        assert membership.evidence[0]["batch_id"] == "painting-toronto-v1"


def test_business_seed_import_is_idempotent() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        service = BusinessSeedService(session)
        first = service.import_seeds([painting_seed()], batch_id="painting-toronto-v1")
        second = service.import_seeds([painting_seed()], batch_id="painting-toronto-v1")

        assert first.businesses_created == 1
        assert second.businesses_created == 0
        assert second.businesses_updated == 1
        assert second.contacts_created == 0
        assert second.source_observations_created == 0
        assert _count(session, BusinessModel) == 1
        assert _count(session, ContactModel) == 1
        assert _count(session, SourceObservationModel) == 1
        assert _count(session, NicheModel) == 1
        assert _count(session, SeedBatchModel) == 1
        assert _count(session, BusinessNicheMembershipModel) == 1


def test_business_seed_import_dedupes_by_phone_without_domain() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        first = painting_seed(website_url=None)
        second = painting_seed(
            company_name="Example Solo Painting Company",
            website_url=None,
            contact_email=None,
        )

        summary = BusinessSeedService(session).import_seeds(
            [first, second],
            batch_id="painting-toronto-v1",
        )

        assert summary.businesses_created == 1
        assert summary.businesses_updated == 1
        assert _count(session, BusinessModel) == 1


def test_business_seed_import_does_not_use_listing_domain_as_business_identity() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        first = painting_seed(
            company_name="First Painter",
            website_url=None,
            phone=None,
            contact_email=None,
            contact_name=None,
            source_url="https://www.openstreetmap.org/node/100",
            external_id="osm:node:100",
        )
        second = painting_seed(
            company_name="Second Painter",
            website_url=None,
            phone=None,
            contact_email=None,
            contact_name=None,
            source_url="https://www.openstreetmap.org/node/200",
            external_id="osm:node:200",
        )

        summary = BusinessSeedService(session).import_seeds(
            [first, second],
            batch_id="painting-toronto-v1",
        )

        assert summary.businesses_created == 2
        assert _count(session, BusinessModel) == 2
        assert {business.domain for business in session.scalars(select(BusinessModel))} == {None}


def test_business_seed_import_rejects_a_mixed_niche_batch_before_writing() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        with pytest.raises(ValueError, match="cannot contain more than one niche"):
            BusinessSeedService(session).import_seeds(
                [
                    painting_seed(),
                    painting_seed(seed_niche="home_service_roofing"),
                ],
                batch_id="mixed-v1",
            )

        assert _count(session, BusinessModel) == 0
        assert _count(session, SeedBatchModel) == 0


def test_business_seed_import_supports_semantic_cache_reuse() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        embedding = FakeEmbeddingClient()
        BusinessSeedService(session, embedding=embedding).import_seeds(
            [painting_seed()],
            batch_id="painting-toronto-v1",
        )

        rows = CanonicalRepository(session, embedding=embedding).list_semantic_discovery_results(
            source_inputs={
                "source_request_prompt": "solo residential painters in Toronto with estimate forms",
                "source_request_intent": {
                    "business_category": "residential painting contractors",
                    "location": "Toronto/GTA",
                    "required_signals": ["estimate forms", "owner contact"],
                    "search_query": "solo residential painters Toronto estimate forms",
                },
            },
            source_input="solo residential painters Toronto estimate forms",
            limit=5,
            min_score=0.2,
            min_results=1,
        )

        assert len(rows) == 1
        assert rows[0]["title"] == "Example Solo Painting Co."
        assert rows[0]["raw"]["semantic_cache_hit"] is True
        assert rows[0]["raw"]["niche_membership"]["niche_slug"] == "home_service_painting"
        assert rows[0]["raw"]["niche_membership"]["seed_batch_id"] == "painting-toronto-v1"


def test_semantic_cache_never_crosses_niche_memberships() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        embedding = FakeEmbeddingClient()
        service = BusinessSeedService(session, embedding=embedding)
        service.import_seeds([painting_seed()], batch_id="painting-test-v1")
        service.import_seeds(
            [
                painting_seed(
                    company_name="Example Toronto Roofing",
                    website_url="https://example-roofing.test",
                    contact_email="owner@example-roofing.test",
                    description="Residential roofing company providing roof repair and replacement.",
                    query="residential roofing contractors in Toronto",
                    signals=["residential roofing", "roof repair"],
                    seed_niche="home_service_roofing",
                )
            ],
            batch_id="roofing-test-v1",
        )

        rows = CanonicalRepository(session, embedding=embedding).list_semantic_discovery_results(
            source_inputs={
                "source_request_intent": {
                    "business_category": "residential painting contractors",
                    "location": "Toronto/GTA",
                    "search_query": "residential painters Toronto",
                },
            },
            source_input="residential painters Toronto",
            limit=5,
            min_score=0.1,
            min_results=1,
        )

        assert [row["title"] for row in rows] == ["Example Solo Painting Co."]
        assert rows[0]["raw"]["niche_membership"]["niche_slug"] == "home_service_painting"


def painting_seed(**overrides) -> BusinessSeedInput:
    data = {
        "company_name": "Example Solo Painting Co.",
        "website_url": "https://example-solo-painting.test",
        "phone": "416-555-0101",
        "contact_email": "owner@example-solo-painting.test",
        "contact_name": "Alex Painter",
        "contact_role": "Owner/Operator",
        "geography": "Toronto, ON",
        "address": "123 Sample St, Toronto, ON",
        "description": (
            "Solo residential painter offering interior painting, exterior painting, "
            "and free estimate requests."
        ),
        "source": "manual_seed",
        "source_url": "https://example-solo-painting.test/contact",
        "query": "solo residential painters in Toronto with estimate forms",
        "signals": ["solo operator", "residential painting", "free estimate", "owner contact"],
        "seed_niche": "home_service_painting",
        "seed_market": "Toronto/GTA",
        "operator_type": "solo",
    }
    data.update(overrides)
    return BusinessSeedInput.model_validate(data)


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _count(session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)
