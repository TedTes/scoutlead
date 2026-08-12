from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from agents.llm import HeuristicLLMClient
from campaigns.schemas import CampaignCreate
from campaigns.service import CampaignService
from conversations.service import ConversationService
from db.session import create_database
from messages.schemas import MessageApproval
from messages.service import MessageService
from products.repository import ProductRepository
from products.schemas import (
    DiscoverySource,
    DiscoverySourceType,
    ProductCreate,
    QualificationCriterion,
)
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
                product_name="QuoteVan",
                product_description="Quoting workflow software for residential painters.",
                target_customer="Residential painters",
                problem_being_solved="Slow quote follow-up loses painting jobs.",
                value_proposition="Create polished quotes and follow-ups faster.",
                target_geography="Ontario, Canada",
                validation_goal="Book customer discovery interviews.",
                qualification_criteria=[
                    QualificationCriterion(
                        label="Residential painting services", weight=3, required=True
                    ),
                    QualificationCriterion(label="Visible contact information", weight=2),
                ],
                preferred_discovery_sources=[
                    DiscoverySource(
                        type=DiscoverySourceType.SEED,
                        value="Maple House Painters|https://example.com|Residential painters serving homeowners|Ontario|hello@example.com",
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
        ).create(CampaignCreate(product_id=product.id, max_leads=3))

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
