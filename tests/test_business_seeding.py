from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from canonical.repository import CanonicalRepository
from db.models import BusinessModel, CampaignModel, ContactModel, LeadModel, SourceObservationModel
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


def test_business_seed_import_populates_canonical_tables_only() -> None:
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
        assert _count(session, LeadModel) == 0
        assert _count(session, CampaignModel) == 0

        business = session.scalar(select(BusinessModel))
        assert business is not None
        assert business.display_name == "Example Solo Painting Co."
        assert business.domain == "example-solo-painting.test"
        assert business.phone == "4165550101"
        assert business.category_key == "home service painting providers"
        assert business.market_key == "toronto gta"

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

