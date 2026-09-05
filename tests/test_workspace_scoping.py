from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate
from db.session import create_database
from leads.repository import LeadRepository
from messages.repository import MessageRepository
from messages.schemas import OutreachDraft
from products.repository import ProductRepository
from products.schemas import ProductCreate, QualificationCriterion
from shared.errors import NotFoundError


def test_products_are_scoped_by_workspace_and_can_share_source_fingerprints() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        first = ProductRepository(session, workspace_id="user:first").create(
            _product("QuoteVan", "source:quotevan")
        )
        second = ProductRepository(session, workspace_id="user:second").create(
            _product("QuoteVan", "source:quotevan")
        )

        assert [product.id for product in ProductRepository(session, workspace_id="user:first").list()] == [
            first.id
        ]
        assert [product.id for product in ProductRepository(session, workspace_id="user:second").list()] == [
            second.id
        ]
        with pytest.raises(NotFoundError):
            ProductRepository(session, workspace_id="user:first").get(second.id)


def test_campaign_lead_and_message_reads_are_scoped_by_product_workspace() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        product = ProductRepository(session, workspace_id="user:first").create(
            _product("QuoteVan", "source:quotevan")
        )
        campaign = CampaignRepository(session, workspace_id="user:first").create(
            CampaignCreate(product_id=product.id, name="Toronto painters", max_leads=5)
        )
        lead = LeadRepository(session, workspace_id="user:first").create_from_search_result(
            campaign.id,
            product.id,
            {
                "title": "Painter Co",
                "url": "https://painter.example",
                "description": "Residential painting contractor",
                "source": "seed",
            },
        )
        message = MessageRepository(session, workspace_id="user:first").create_draft(
            campaign.id,
            product.id,
            lead.id,
            OutreachDraft(
                subject="Quick question",
                body="Hi, open to a quick question?",
                personalization_notes=[],
                approach_tag="test",
            ),
        )

        other_campaigns = CampaignRepository(session, workspace_id="user:second")
        other_leads = LeadRepository(session, workspace_id="user:second")
        other_messages = MessageRepository(session, workspace_id="user:second")

        with pytest.raises(NotFoundError):
            other_campaigns.get(campaign.id)
        with pytest.raises(NotFoundError):
            other_leads.get(lead.id)
        with pytest.raises(NotFoundError):
            other_messages.get(message.id)


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _product(name: str, source_fingerprint: str) -> ProductCreate:
    return ProductCreate(
        product_name=name,
        product_description="Quote software for residential service contractors.",
        target_customer="Residential painting contractors",
        problem_being_solved="Quoting takes too long after an in-person estimate.",
        value_proposition="Create and send quote-ready service pages faster.",
        target_geography="Toronto, Ontario, Canada",
        validation_goal="Find contractors to interview.",
        qualification_criteria=[
            QualificationCriterion(
                label="Residential painting",
                description="Business serves residential painting customers.",
                weight=2,
                required=True,
            )
        ],
        preferred_discovery_sources=[],
        outreach_objective="Ask for feedback on quoting workflow.",
        constraints=["Human approval required before sending."],
        source_fingerprint=source_fingerprint,
    )
