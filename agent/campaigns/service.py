from sqlalchemy.orm import Session

from agents.llm import LLMClient
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, CampaignRead, CampaignRunSummary, CampaignStage, CampaignStatus
from conversations.repository import ConversationRepository
from conversations.schemas import ConversationRead
from db.models import CampaignModel
from evaluation.campaign_metrics import calculate_campaign_metrics
from evaluation.schemas import CampaignMetrics
from leads.repository import LeadRepository
from leads.schemas import LeadRead
from memory.repository import MemoryRepository
from messages.repository import MessageRepository
from messages.schemas import MessageRead
from products.repository import ProductRepository
from products.schemas import ProductRead
from tools.browser import DirectHttpBrowserTool
from tools.search import SearchTool
from workflows.discovery import DiscoveryWorkflow
from workflows.outreach import OutreachWorkflow
from workflows.qualification import QualificationWorkflow
from workflows.research import ResearchWorkflow


class CampaignService:
    def __init__(
        self,
        *,
        session: Session,
        llm: LLMClient,
        search_tool: SearchTool,
        browser: DirectHttpBrowserTool,
    ) -> None:
        self.session = session
        self.llm = llm
        self.search_tool = search_tool
        self.browser = browser
        self.products = ProductRepository(session)
        self.campaigns = CampaignRepository(session)
        self.leads = LeadRepository(session)
        self.messages = MessageRepository(session)
        self.conversations = ConversationRepository(session)
        self.memory = MemoryRepository(session)

    def create(self, campaign: CampaignCreate) -> CampaignModel:
        self.products.get(campaign.product_id)
        return self.campaigns.create(campaign)

    def list(self) -> list[CampaignModel]:
        return self.campaigns.list()

    def get(self, campaign_id: str) -> CampaignModel:
        return self.campaigns.get(campaign_id)

    def delete(self, campaign_id: str) -> None:
        self.campaigns.delete(campaign_id)

    def pause(self, campaign_id: str) -> CampaignModel:
        return self.campaigns.update_status(campaign_id, CampaignStatus.PAUSED)

    def resume(self, campaign_id: str) -> CampaignModel:
        campaign = self.campaigns.get(campaign_id)
        stage_to_status = {
            CampaignStage.DISCOVERY.value: CampaignStatus.DISCOVERING,
            CampaignStage.RESEARCH.value: CampaignStatus.RESEARCHING,
            CampaignStage.QUALIFICATION.value: CampaignStatus.QUALIFYING,
            CampaignStage.OUTREACH.value: CampaignStatus.AWAITING_APPROVAL,
            CampaignStage.RESPONSE.value: CampaignStatus.TRACKING,
            CampaignStage.COMPLETE.value: CampaignStatus.COMPLETED,
        }
        return self.campaigns.update_status(
            campaign_id, stage_to_status.get(campaign.stage, CampaignStatus.TRACKING)
        )

    def run_campaign(self, campaign_id: str) -> CampaignRunSummary:
        campaign = self.campaigns.get(campaign_id)
        product = ProductRead.model_validate(self.products.get(campaign.product_id))
        campaign_read = CampaignRead.model_validate(campaign)

        discovered = DiscoveryWorkflow(
            campaigns=self.campaigns,
            leads=self.leads,
            memory=self.memory,
            search_tool=self.search_tool,
        ).run(product, campaign_read)

        campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        researched = ResearchWorkflow(
            campaigns=self.campaigns,
            leads=self.leads,
            memory=self.memory,
            browser=self.browser,
            llm=self.llm,
        ).run(product, campaign_read)

        campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        qualified = QualificationWorkflow(
            campaigns=self.campaigns,
            leads=self.leads,
            memory=self.memory,
            llm=self.llm,
        ).run(product, campaign_read)

        campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        drafts = OutreachWorkflow(
            campaigns=self.campaigns,
            leads=self.leads,
            messages=self.messages,
            memory=self.memory,
            llm=self.llm,
        ).run(product, campaign_read)

        return CampaignRunSummary(
            campaign=CampaignRead.model_validate(self.campaigns.get(campaign_id)),
            discovered_lead_count=len(discovered),
            researched_lead_count=len(researched),
            qualified_lead_count=sum(1 for lead in qualified if lead.qualification and lead.qualification.qualified),
            drafted_message_count=len(drafts),
        )

    def metrics(self, campaign_id: str) -> CampaignMetrics:
        leads = [
            LeadRead.model_validate(model)
            for model in self.leads.list_by_campaign(campaign_id)
        ]
        messages = [
            MessageRead.model_validate(model)
            for model in self.messages.list_by_campaign(campaign_id)
        ]
        conversations = [
            ConversationRead.model_validate(model)
            for model in self.conversations.list_by_campaign(campaign_id)
        ]
        return calculate_campaign_metrics(
            leads=leads, messages=messages, conversations=conversations
        )
