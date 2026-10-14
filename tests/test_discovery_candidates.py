from datetime import UTC, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from campaigns.schemas import LeadSeedInput
from db.session import create_database
from leads.repository import LeadRepository
from leads.schemas import LeadReviewStatus, LeadUpdate
from products.repository import ProductRepository
from products.schemas import DiscoverySource, DiscoverySourceType, ProductCreate, QualificationCriterion


def test_lead_review_state_and_shortlist_are_persisted() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(product_input())
        lead = LeadRepository(session).create_from_seed(
            "campaign_review_state",
            product.id,
            LeadSeedInput(
                company_name="Cedar & Sons Painting",
                website_url="https://cedarpaint.example",
                geography="Austin, TX",
                description="Residential painting company",
            ),
        )

        updated = LeadRepository(session).update(
            lead.id,
            LeadUpdate(
                review_status=LeadReviewStatus.GOOD_FIT,
                review_note="Owner-operated and reachable.",
                shortlisted=True,
            ),
        )

        assert updated.review_status == LeadReviewStatus.GOOD_FIT.value
        assert updated.review_note == "Owner-operated and reachable."
        assert updated.reviewed_at is not None
        assert updated.shortlisted_at is not None

        unshortlisted = LeadRepository(session).update(
            lead.id,
            LeadUpdate(shortlisted=False),
        )
        assert unshortlisted.shortlisted_at is None


def product_input() -> ProductCreate:
    return ProductCreate(
        product_name="QuoteVan",
        product_description="Mobile quoting app for residential painters.",
        target_customer="Residential painting companies in the United States",
        problem_being_solved="Painters need to create professional job quotes after walkthroughs.",
        value_proposition="Create customer-ready quotes faster.",
        target_geography="United States",
        validation_goal="Book discovery interviews.",
        qualification_criteria=[
            QualificationCriterion(
                id="painting_company",
                label="Residential painting company",
                description="Provides painting services to homeowners.",
                weight=1,
                required=True,
                evidence_required=True,
            )
        ],
        preferred_discovery_sources=[
            DiscoverySource(
                type=DiscoverySourceType.WEB_SEARCH,
                value='"residential painting company" "free estimate" "contact us"',
            )
        ],
        outreach_objective="Ask for a discovery conversation.",
        constraints=["Human approval required before sending."],
        source_evidence={"created_at": datetime.now(UTC).isoformat()},
    )
