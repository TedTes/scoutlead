from __future__ import annotations

from sqlalchemy.orm import Session

from agents.llm import LLMClient
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead
from conversations.repository import ConversationRepository
from conversations.schemas import ConversationRead
from evaluation.campaign_metrics import calculate_campaign_metrics
from insights.repository import CampaignInsightRepository
from insights.schemas import CampaignInsightRead
from insights.synthesizer import InsightSynthesizer
from leads.repository import LeadRepository
from leads.schemas import LeadRead
from messages.repository import MessageRepository
from messages.schemas import MessageRead
from products.repository import ProductRepository
from products.schemas import ProductRead
from shared.errors import NotFoundError


class CampaignInsightService:
    def __init__(
        self,
        *,
        session: Session,
        llm: LLMClient,
        workspace_id: str | None = None,
    ) -> None:
        self.products = ProductRepository(session, workspace_id=workspace_id)
        self.campaigns = CampaignRepository(session, workspace_id=workspace_id)
        self.leads = LeadRepository(session, workspace_id=workspace_id)
        self.messages = MessageRepository(session, workspace_id=workspace_id)
        self.conversations = ConversationRepository(session, workspace_id=workspace_id)
        self.insights = CampaignInsightRepository(session)
        self.synthesizer = InsightSynthesizer(llm)

    def latest(self, campaign_id: str) -> CampaignInsightRead:
        latest = self.insights.latest_for_campaign(campaign_id)
        if latest is None:
            raise NotFoundError("campaign insights not found", {"campaign_id": campaign_id})
        return CampaignInsightRead.model_validate(latest)

    def generate(self, campaign_id: str) -> CampaignInsightRead:
        campaign = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        product = ProductRead.model_validate(self.products.get(campaign.product_id))
        leads = [LeadRead.model_validate(model) for model in self.leads.list_by_campaign(campaign_id)]
        messages = [
            MessageRead.model_validate(model) for model in self.messages.list_by_campaign(campaign_id)
        ]
        conversations = [
            ConversationRead.model_validate(model)
            for model in self.conversations.list_by_campaign(campaign_id)
        ]
        metrics = calculate_campaign_metrics(
            leads=leads,
            messages=messages,
            conversations=conversations,
            goal_type=campaign.goal_type,
        ).model_dump(mode="json")
        draft = self.synthesizer.synthesize(
            product=product,
            campaign=campaign,
            leads=leads,
            messages=messages,
            conversations=conversations,
            metrics=metrics,
        )
        model = self.insights.create(
            campaign_id=campaign.id,
            product_id=product.id,
            goal_type=campaign.goal_type.value,
            draft=draft,
            metrics_snapshot=metrics,
        )
        return CampaignInsightRead.model_validate(model)
