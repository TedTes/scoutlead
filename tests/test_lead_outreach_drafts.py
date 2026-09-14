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
from messages.schemas import (
    CampaignMessageApproval,
    CampaignMessageSend,
    CampaignOutreachAudience,
    CampaignOutreachDraftCreate,
    MessageApproval,
    MessageReplyMark,
    MessageStatus,
    OutreachDraft,
)
from messages.service import MessageService
from products.repository import ProductRepository
from shared.errors import ConfigurationError, ConflictError
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


class FailingEmail:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def bind_session(self, session):
        return self

    def send(self, *, product, lead, message):
        raise self.exc


def _create_campaign_fixture(session):
    product = ProductRepository(session).create(product_input())
    campaign = CampaignRepository(session).create(
        CampaignCreate(product_id=product.id, name="Painters Toronto", max_leads=5)
    )
    return product, campaign, LeadRepository(session)


def _create_fit_lead(
    lead_repo: LeadRepository,
    *,
    campaign_id: str,
    product_id: str,
    company_name: str,
    email: str | None,
    verified: bool = True,
    shortlisted: bool = False,
):
    lead = lead_repo.create_from_seed(
        campaign_id,
        product_id,
        LeadSeedInput(
            company_name=company_name,
            website_url=f"https://{company_name.lower().replace(' ', '-')}.example",
            contact_email=email,
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
    if shortlisted:
        lead_repo.update(lead.id, LeadUpdate(shortlisted=True))
    if verified and email:
        lead_repo.attach_verification(
            lead.id,
            LeadVerification(
                status=ContactVerificationStatus.VALID,
                provider="syntax",
                reason="Email syntax is valid.",
                score=80,
            ),
        )
    return lead_repo.get(lead.id)


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


def test_campaign_template_drafts_selected_contacts_and_reuses_existing() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product, campaign, lead_repo = _create_campaign_fixture(session)
        selected = _create_fit_lead(
            lead_repo,
            campaign_id=campaign.id,
            product_id=product.id,
            company_name="Cedar Sons Painting",
            email="owner@cedar.example",
        )
        _create_fit_lead(
            lead_repo,
            campaign_id=campaign.id,
            product_id=product.id,
            company_name="Maple Ridge Painting",
            email="owner@maple.example",
        )

        service = MessageService(session=session, email=EmailTool())
        result = service.create_campaign_outreach_drafts(
            campaign.id,
            CampaignOutreachDraftCreate(
                audience=CampaignOutreachAudience.SELECTED,
                lead_ids=[selected.id],
                subject="Question for {{business_name}}",
                body=(
                    "Hello {{recipient_name}}, {{fit_reason}} "
                    "Would {{product_name}} help your quoting workflow?"
                ),
            ),
        )
        second_result = service.create_campaign_outreach_drafts(
            campaign.id,
            CampaignOutreachDraftCreate(
                audience=CampaignOutreachAudience.SELECTED,
                lead_ids=[selected.id],
                subject="Question for {{business_name}}",
                body="Hello {{recipient_name}}",
            ),
        )

        assert result.created_count == 1
        assert result.reused_count == 0
        assert result.skipped == []
        assert result.messages[0].subject == "Question for Cedar Sons Painting"
        assert "Hello Cedar Sons Painting team" in result.messages[0].body
        assert "Residential painting business with contact info." in result.messages[0].body
        assert lead_repo.get(selected.id).shortlisted_at is not None
        assert lead_repo.get(selected.id).status == LeadStatus.AWAITING_APPROVAL.value
        assert second_result.created_count == 0
        assert second_result.reused_count == 1
        assert second_result.messages[0].id == result.messages[0].id
        assert len(service.messages.list_by_campaign(campaign.id)) == 1


def test_campaign_template_drafts_skips_unready_contacts() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product, campaign, lead_repo = _create_campaign_fixture(session)
        eligible = _create_fit_lead(
            lead_repo,
            campaign_id=campaign.id,
            product_id=product.id,
            company_name="Verified Painter",
            email="owner@verified.example",
        )
        _create_fit_lead(
            lead_repo,
            campaign_id=campaign.id,
            product_id=product.id,
            company_name="No Email Painter",
            email=None,
            verified=False,
        )
        _create_fit_lead(
            lead_repo,
            campaign_id=campaign.id,
            product_id=product.id,
            company_name="Unverified Painter",
            email="owner@unverified.example",
            verified=False,
        )

        result = MessageService(session=session, email=EmailTool()).create_campaign_outreach_drafts(
            campaign.id,
            CampaignOutreachDraftCreate(
                audience=CampaignOutreachAudience.READY_CONTACTS,
                subject="Quote question for {{business_name}}",
                body="Hello {{recipient_name}}, would {{product_name}} help?",
            ),
        )

        assert result.created_count == 1
        assert [message.lead_id for message in result.messages] == [eligible.id]
        skipped = {skip.company_name: skip.reason for skip in result.skipped}
        assert skipped["No Email Painter"] == "Find a reachable email before preparing outreach."
        assert skipped["Unverified Painter"] == "Verify the email before preparing outreach."


def test_campaign_bulk_send_requires_batch_approval_first() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product, campaign, lead_repo = _create_campaign_fixture(session)
        lead = _create_fit_lead(
            lead_repo,
            campaign_id=campaign.id,
            product_id=product.id,
            company_name="Verified Painter",
            email="owner@verified.example",
        )

        service = MessageService(session=session, email=EmailTool())
        draft_result = service.create_campaign_outreach_drafts(
            campaign.id,
            CampaignOutreachDraftCreate(
                audience=CampaignOutreachAudience.SELECTED,
                lead_ids=[lead.id],
                subject="Quote question for {{business_name}}",
                body="Hello {{recipient_name}}, would {{product_name}} help?",
            ),
        )
        message = draft_result.messages[0]

        blocked_send = service.send_campaign_messages(
            campaign.id,
            CampaignMessageSend(message_ids=[message.id]),
        )
        approved = service.approve_campaign_messages(
            campaign.id,
            CampaignMessageApproval(message_ids=[message.id], approved_by="operator"),
        )
        sent = service.send_campaign_messages(
            campaign.id,
            CampaignMessageSend(message_ids=[message.id]),
        )

        assert blocked_send.sent_count == 0
        assert blocked_send.skipped[0].reason == "Approve this draft before sending."
        assert service.messages.get(message.id).status == MessageStatus.SENT.value
        assert approved.approved_count == 1
        assert sent.sent_count == 1
        assert sent.messages[0].status == MessageStatus.SENT
        assert lead_repo.get(lead.id).status == LeadStatus.SENT.value


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


def test_send_failure_records_user_message_without_advancing_campaign() -> None:
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

        service = MessageService(
            session=session,
            email=FailingEmail(
                ConfigurationError(
                    "Gmail is not connected for this account",
                    {"user_message": "Connect Gmail in Integrations before sending outreach."},
                )
            ),
            llm=DraftLLM(),
        )
        message = service.create_outreach_draft_for_lead(lead.id)
        service.approve(message.id, MessageApproval(approved_by="operator"))
        campaign_status_before = CampaignRepository(session).get(campaign.id).status

        with pytest.raises(ConfigurationError):
            service.send(message.id)

        failed = service.messages.get(message.id)
        assert failed.status == MessageStatus.FAILED.value
        assert failed.failure_reason == "Connect Gmail in Integrations before sending outreach."
        assert CampaignRepository(session).get(campaign.id).status == campaign_status_before


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
