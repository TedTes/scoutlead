from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, LeadSeedInput
from canonical.repository import CanonicalRepository
from db.models import BusinessModel, ContactModel, SourceObservationModel
from db.session import create_database
from leads.repository import LeadRepository
from leads.schemas import ContactVerificationStatus, LeadVerification
from products.repository import ProductRepository
from products.schemas import (
    DiscoverySource,
    DiscoverySourceType,
    ProductCreate,
    QualificationCriterion,
)


def test_untrusted_raw_email_is_observed_but_not_promoted_to_contact() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        link = CanonicalRepository(session).upsert_from_discovery_result(
            company_name="Scarborough Painting Company",
            geography="Scarborough, ON",
            source="configured_search",
            raw={"contact_email": "directory@example.test"},
            allow_raw_contact_email=False,
        )

        observation = session.get(SourceObservationModel, link.source_observation_id)
        assert link.contact_id is None
        assert session.scalar(select(func.count()).select_from(ContactModel)) == 0
        assert observation is not None
        assert observation.raw_payload["contact_email"] == "directory@example.test"


def test_leads_from_repeat_runs_share_canonical_business_and_contact() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(product_input())
        first_campaign = CampaignRepository(session).create(
            CampaignCreate(product_id=product.id, name="Painters Toronto 1", max_leads=10)
        )
        second_campaign = CampaignRepository(session).create(
            CampaignCreate(product_id=product.id, name="Painters Toronto 2", max_leads=10)
        )
        seed = LeadSeedInput(
            company_name="Top Shelf Painting & Staining Inc.",
            website_url="https://topshelfhomes.ca",
            contact_email="adam@topshelfhomes.ca",
            geography="Toronto, ON",
            description="Residential and commercial painting contractor",
            source="google_places",
            raw={
                "id": "places/top-shelf",
                "query": "residential painters Toronto ON",
                "nationalPhoneNumber": "(437) 772-4190",
                "contactName": "Adam Johns",
            },
        )

        first_lead = LeadRepository(session).create_from_seed(first_campaign.id, product.id, seed)
        second_lead = LeadRepository(session).create_from_seed(second_campaign.id, product.id, seed)

        assert first_lead.id != second_lead.id
        assert first_lead.business_id == second_lead.business_id
        assert first_lead.contact_id == second_lead.contact_id
        assert session.scalar(select(func.count()).select_from(BusinessModel)) == 1
        assert session.scalar(select(func.count()).select_from(ContactModel)) == 1
        assert session.scalar(select(func.count()).select_from(SourceObservationModel)) == 1


def test_lead_verification_updates_canonical_contact() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(product_input())
        campaign = CampaignRepository(session).create(
            CampaignCreate(product_id=product.id, name="Painters Toronto", max_leads=10)
        )
        lead = LeadRepository(session).create_from_seed(
            campaign.id,
            product.id,
            LeadSeedInput(
                company_name="Top Shelf Painting & Staining Inc.",
                website_url="https://topshelfhomes.ca",
                contact_email="adam@topshelfhomes.ca",
                geography="Toronto, ON",
                description="Residential and commercial painting contractor",
            ),
        )

        assert lead.contact_id is not None
        LeadRepository(session).attach_verification(
            lead.id,
            LeadVerification(
                status=ContactVerificationStatus.VALID,
                provider="bouncer",
                reason="Mailbox accepted.",
                score=95,
                details={"result": "deliverable"},
            ),
        )

        contact = session.get(ContactModel, lead.contact_id)
        assert contact is not None
        assert contact.verification_status == ContactVerificationStatus.VALID.value
        assert contact.verification_provider == "bouncer"
        assert contact.verification_score == 95
        assert contact.verification_details == {"result": "deliverable"}


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
    )
