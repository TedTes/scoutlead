import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, LeadSeedInput
from db.session import create_database
from leads.repository import LeadRepository
from leads.schemas import AgentFitStatus, LeadReviewStatus, LeadStatus, LeadUpdate, QualificationResult
from messages.schemas import MessageApproval, MessageStatus, OutreachDraft
from messages.service import MessageService
from products.repository import ProductRepository
from shared.errors import ConflictError
from tests.test_discovery_candidates import product_input
from tools.email import EmailTool


class DraftLLM:
    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model,
        context: dict | None = None,
    ):
        assert task == "outreach_draft"
        assert response_model is OutreachDraft
        return OutreachDraft(
            subject="QuoteVan question",
            body="Open to sharing how you handle quotes today?",
            personalization_notes=["Mentions residential painting."],
            approach_tag="manual_shortlist",
        )


def test_shortlisted_lead_can_generate_one_pending_outreach_draft() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(product_input())
        campaign = CampaignRepository(session).create(
            CampaignCreate(product_id=product.id, name="Painters Toronto", max_leads=5)
        )
        lead_repo = LeadRepository(session)
        lead = lead_repo.create_from_seed(
            campaign.id,
            product.id,
            LeadSeedInput(
                company_name="Cedar & Sons Painting",
                website_url="https://cedarpaint.example",
                contact_email="owner@cedarpaint.example",
                geography="Toronto, ON",
                description="Residential painting company",
            ),
        )
        lead_repo.update(
            lead.id,
            LeadUpdate(review_status=LeadReviewStatus.GOOD_FIT, shortlisted=True),
        )

        service = MessageService(session=session, email=EmailTool(), llm=DraftLLM())
        message = service.create_outreach_draft_for_lead(lead.id)
        second_call = service.create_outreach_draft_for_lead(lead.id)

        assert message.id == second_call.id
        assert message.status == MessageStatus.PENDING_APPROVAL
        assert message.subject == "QuoteVan question"
        assert lead_repo.get(lead.id).status == LeadStatus.AWAITING_APPROVAL.value


def test_unreviewed_lead_without_agent_fit_cannot_be_shortlisted() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(product_input())
        campaign = CampaignRepository(session).create(
            CampaignCreate(product_id=product.id, name="Painters Toronto", max_leads=5)
        )
        lead = LeadRepository(session).create_from_seed(
            campaign.id,
            product.id,
            LeadSeedInput(
                company_name="Cedar & Sons Painting",
                website_url="https://cedarpaint.example",
                contact_email="owner@cedarpaint.example",
                geography="Toronto, ON",
                description="Residential painting company",
            ),
        )

        with pytest.raises(ConflictError):
            LeadRepository(session).update(lead.id, LeadUpdate(shortlisted=True))


def test_agent_good_fit_can_be_shortlisted_before_manual_review() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(product_input())
        campaign = CampaignRepository(session).create(
            CampaignCreate(product_id=product.id, name="Painters Toronto", max_leads=5)
        )
        lead_repo = LeadRepository(session)
        lead = lead_repo.create_from_seed(
            campaign.id,
            product.id,
            LeadSeedInput(
                company_name="Cedar & Sons Painting",
                website_url="https://cedarpaint.example",
                contact_email="owner@cedarpaint.example",
                geography="Toronto, ON",
                description="Residential painting company",
            ),
        )
        lead_repo.attach_qualification(
            lead.id,
            QualificationResult(
                qualified=True,
                fit_status=AgentFitStatus.GOOD_FIT,
                score=90,
                rationale="Residential painting business with contact info.",
                positive_signals=["Residential painting business"],
                missing_evidence=[],
                risks=[],
                recommended_next_step="Draft outreach.",
            ),
        )

        shortlisted = lead_repo.update(lead.id, LeadUpdate(shortlisted=True))

        assert shortlisted.shortlisted_at is not None


def test_not_fit_review_clears_shortlist_and_blocks_sending() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(product_input())
        campaign = CampaignRepository(session).create(
            CampaignCreate(product_id=product.id, name="Painters Toronto", max_leads=5)
        )
        lead_repo = LeadRepository(session)
        lead = lead_repo.create_from_seed(
            campaign.id,
            product.id,
            LeadSeedInput(
                company_name="Cedar & Sons Painting",
                website_url="https://cedarpaint.example",
                contact_email="owner@cedarpaint.example",
                geography="Toronto, ON",
                description="Residential painting company",
            ),
        )
        lead_repo.update(
            lead.id,
            LeadUpdate(review_status=LeadReviewStatus.GOOD_FIT, shortlisted=True),
        )

        service = MessageService(session=session, email=EmailTool(), llm=DraftLLM())
        message = service.create_outreach_draft_for_lead(lead.id)
        service.approve(message.id, MessageApproval(approved_by="operator"))
        not_fit = lead_repo.update(lead.id, LeadUpdate(review_status=LeadReviewStatus.NOT_FIT))

        assert not_fit.shortlisted_at is None
        with pytest.raises(ConflictError):
            service.send(message.id)
