from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import pytest

from agents.llm import HeuristicLLMClient
from campaigns.schemas import CampaignCreate
from campaigns.service import CampaignService
from conversations.schemas import FollowUpAction, ManualClassificationCreate, ResponseIntent
from conversations.service import ConversationService
from db.session import create_database
from messages.schemas import MessageApproval, MessageUpdate
from messages.service import MessageService
from products.repository import ProductRepository
from products.schemas import (
    DiscoverySource,
    DiscoverySourceType,
    ProductCreate,
    QualificationCriterion,
)
from shared.errors import ConflictError
from tools.browser import DirectHttpBrowserTool
from tools.email import EmailTool
from tools.search import SearchTool


def test_end_to_end_campaign_requires_approval_before_send() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(
            ProductCreate(
                product_name="Test Product",
                product_description="Software product used by the smoke test.",
                target_customer="Target customer segment",
                problem_being_solved="A customer workflow takes too long.",
                value_proposition="Improve the workflow enough to justify discovery.",
                target_geography="Test geography",
                validation_goal="Book customer discovery interviews.",
                qualification_criteria=[
                    QualificationCriterion(
                        label="Matches target customer", weight=3, required=True
                    ),
                    QualificationCriterion(label="Visible contact information", weight=2),
                ],
                preferred_discovery_sources=[
                    DiscoverySource(
                        type=DiscoverySourceType.SEED,
                        value="Test Lead Company|https://example.com|Matches target customer|Test geography|hello@example.com",
                    )
                ],
                outreach_objective="Ask for a 20-minute discovery interview.",
                constraints=["Human approval required before sending."],
            )
        )
        campaign = CampaignService(
            session=session,
            llm=HeuristicLLMClient(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
        ).create(CampaignCreate(product_id=product.id, name="Smoke test campaign", max_leads=3))

        summary = CampaignService(
            session=session,
            llm=HeuristicLLMClient(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
        ).run_campaign(campaign.id)

        assert summary.discovered_lead_count == 1
        assert summary.drafted_message_count == 1

        messages = CampaignService(
            session=session,
            llm=HeuristicLLMClient(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
        ).metrics(campaign.id)
        assert messages.pending_approval_count == 1

        message_id = session.execute(text("select id from messages")).scalar_one()
        message_service = MessageService(session=session, email=EmailTool())
        with pytest.raises(ConflictError):
            message_service.send(message_id)

        edited = message_service.update(
            message_id,
            MessageUpdate(subject="Edited validation question", body="Hi there,\n\nOpen to talking?"),
        )
        assert edited.subject == "Edited validation question"

        approved = message_service.approve(
            message_id, MessageApproval(approved_by="test@example.com")
        )
        assert approved.status == "approved"

        sent = message_service.send(message_id)
        assert sent.status == "sent"

        conversation_id = session.execute(text("select id from conversations")).scalar_one()
        conversation = ConversationService(session=session, llm=HeuristicLLMClient()).classify_response(
            conversation_id, "Sure, happy to schedule an interview next week."
        )
        assert conversation.events[-1].classification.intent == "interview_request"

        reclassified = ConversationService(
            session=session, llm=HeuristicLLMClient()
        ).manually_classify(
            conversation_id,
            ManualClassificationCreate(
                intent=ResponseIntent.INTERESTED,
                confidence=100,
                rationale="Operator confirmed this is interested.",
                follow_up_action=FollowUpAction.REPLY,
            ),
        )
        assert reclassified.events[-1].direction == "internal"
        assert reclassified.events[-1].classification.intent == "interested"


def test_campaign_with_no_drafts_completes_without_approval_queue() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(
            ProductCreate(
                product_name="No Lead Product",
                product_description="Software product used by the no-lead workflow test.",
                target_customer="Target customer segment",
                problem_being_solved="A customer workflow takes too long.",
                value_proposition="Improve the workflow enough to justify discovery.",
                target_geography="Test geography",
                validation_goal="Book customer discovery interviews.",
                qualification_criteria=[
                    QualificationCriterion(label="Matches target customer", weight=3, required=True),
                ],
                preferred_discovery_sources=[
                    DiscoverySource(type=DiscoverySourceType.WEB_SEARCH, value="no configured search"),
                ],
                outreach_objective="Ask for a 20-minute discovery interview.",
                constraints=["Human approval required before sending."],
            )
        )
        campaign = CampaignService(
            session=session,
            llm=HeuristicLLMClient(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
        ).create(CampaignCreate(product_id=product.id, name="No draft campaign", max_leads=3))

        summary = CampaignService(
            session=session,
            llm=HeuristicLLMClient(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
        ).run_campaign(campaign.id)

        assert summary.discovered_lead_count == 0
        assert summary.drafted_message_count == 0
        assert summary.campaign.status == "completed"
        assert summary.campaign.stage == "complete"
        metrics = CampaignService(
            session=session,
            llm=HeuristicLLMClient(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
        ).metrics(campaign.id)
        assert metrics.pending_approval_count == 0
