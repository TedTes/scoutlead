import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, LeadSeedInput
from db.session import create_database
from leads.repository import LeadRepository
from leads.schemas import (
    AgentFitStatus,
    ContactPolicyStatus,
    ContactVerificationStatus,
    LeadContactPolicyUpdate,
    LeadReviewStatus,
    LeadStatus,
    LeadUpdate,
    LeadVerification,
    QualificationResult,
    SuppressionScope,
)
from messages.schemas import MessageApproval, MessageReplyMark, MessageStatus, OutreachDraft
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
        lead_repo.attach_verification(
            lead.id,
            LeadVerification(
                status=ContactVerificationStatus.VALID,
                provider="syntax",
                reason="Email syntax is valid.",
                score=80,
            ),
        )

        service = MessageService(session=session, email=EmailTool(), llm=DraftLLM())
        message = service.create_outreach_draft_for_lead(lead.id)
        second_call = service.create_outreach_draft_for_lead(lead.id)

        assert message.id == second_call.id
        assert message.status == MessageStatus.PENDING_APPROVAL
        assert message.subject == "QuoteVan question"
        assert lead_repo.get(lead.id).status == LeadStatus.AWAITING_APPROVAL.value


def test_suppressed_lead_blocks_shortlist_and_future_matching() -> None:
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
        blocked = lead_repo.update_contact_policy(
            lead.id,
            LeadContactPolicyUpdate(
                status=ContactPolicyStatus.SUPPRESSED,
                reason="Asked not to be contacted.",
                scope=SuppressionScope.PRODUCT,
            ),
        )

        assert blocked.contact_policy_status == ContactPolicyStatus.SUPPRESSED.value
        assert blocked.shortlisted_at is None
        with pytest.raises(ConflictError):
            lead_repo.update(lead.id, LeadUpdate(review_status=LeadReviewStatus.GOOD_FIT, shortlisted=True))

        next_campaign = CampaignRepository(session).create(
            CampaignCreate(product_id=product.id, name="Painters Toronto rerun", max_leads=5)
        )
        rediscovered = lead_repo.create_from_seed(
            next_campaign.id,
            product.id,
            LeadSeedInput(
                company_name="Cedar Painting Again",
                website_url="https://cedarpaint.example/services",
                contact_email="owner@cedarpaint.example",
                geography="Toronto, ON",
                description="Residential painting company",
            ),
        )

        assert rediscovered.contact_policy_status == ContactPolicyStatus.SUPPRESSED.value
        assert rediscovered.contact_policy_reason == "Asked not to be contacted."


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


def test_shortlisted_good_fit_lead_must_be_verified_before_drafting() -> None:
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

        with pytest.raises(ConflictError):
            MessageService(session=session, email=EmailTool(), llm=DraftLLM()).create_outreach_draft_for_lead(
                lead.id
            )


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


def test_draft_shortlist_skips_unverified_and_not_fit_leads() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(product_input())
        campaign = CampaignRepository(session).create(
            CampaignCreate(product_id=product.id, name="Painters Toronto", max_leads=5)
        )
        lead_repo = LeadRepository(session)
        verified = lead_repo.create_from_seed(
            campaign.id,
            product.id,
            LeadSeedInput(
                company_name="Verified Painter",
                website_url="https://verified.example",
                contact_email="owner@verified.example",
                geography="Toronto, ON",
                description="Residential painting company",
            ),
        )
        unverified = lead_repo.create_from_seed(
            campaign.id,
            product.id,
            LeadSeedInput(
                company_name="Unverified Painter",
                website_url="https://unverified.example",
                contact_email="owner@unverified.example",
                geography="Toronto, ON",
                description="Residential painting company",
            ),
        )
        not_fit = lead_repo.create_from_seed(
            campaign.id,
            product.id,
            LeadSeedInput(
                company_name="Not Fit Directory",
                website_url="https://directory.example",
                contact_email="hello@directory.example",
                geography="Toronto, ON",
                description="Directory page",
            ),
        )
        for lead in [verified, unverified, not_fit]:
            lead_repo.update(
                lead.id,
                LeadUpdate(review_status=LeadReviewStatus.GOOD_FIT, shortlisted=True),
            )
        lead_repo.attach_verification(
            verified.id,
            LeadVerification(
                status=ContactVerificationStatus.VALID,
                provider="syntax",
                reason="Email syntax is valid.",
                score=80,
            ),
        )
        lead_repo.attach_verification(
            not_fit.id,
            LeadVerification(
                status=ContactVerificationStatus.VALID,
                provider="syntax",
                reason="Email syntax is valid.",
                score=80,
            ),
        )
        lead_repo.update(not_fit.id, LeadUpdate(review_status=LeadReviewStatus.NOT_FIT))

        messages = MessageService(session=session, email=EmailTool(), llm=DraftLLM()).create_outreach_drafts_for_run(
            campaign.id
        )

        assert [message.lead_id for message in messages] == [verified.id]


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
        lead_repo.attach_verification(
            lead.id,
            LeadVerification(
                status=ContactVerificationStatus.VALID,
                provider="syntax",
                reason="Email syntax is valid.",
                score=80,
            ),
        )

        service = MessageService(session=session, email=EmailTool(), llm=DraftLLM())
        message = service.create_outreach_draft_for_lead(lead.id)
        service.approve(message.id, MessageApproval(approved_by="operator"))
        not_fit = lead_repo.update(lead.id, LeadUpdate(review_status=LeadReviewStatus.NOT_FIT))

        assert not_fit.shortlisted_at is None
        with pytest.raises(ConflictError):
            service.send(message.id)


def test_sent_message_can_be_marked_replied() -> None:
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
        lead_repo.attach_verification(
            lead.id,
            LeadVerification(
                status=ContactVerificationStatus.VALID,
                provider="syntax",
                reason="Email syntax is valid.",
                score=80,
            ),
        )

        service = MessageService(session=session, email=EmailTool(), llm=DraftLLM())
        message = service.create_outreach_draft_for_lead(lead.id)
        service.approve(message.id, MessageApproval(approved_by="operator"))
        sent = service.send(message.id)
        replied = service.mark_replied(sent.id, MessageReplyMark(body="They replied with interest."))

        assert replied.status == MessageStatus.REPLIED
        assert lead_repo.get(lead.id).status == LeadStatus.RESPONDED.value
