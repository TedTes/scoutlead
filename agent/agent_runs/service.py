from __future__ import annotations

from sqlalchemy.orm import Session

from agent_runs.repository import AgentRunRepository
from agent_runs.schemas import AgentRunCreate, AgentRunDetail, AgentRunRead, AgentStepRead, ToolCallRead
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead, CampaignStatus
from products.repository import ProductRepository
from products.schemas import ProductRead
from shared.errors import ConflictError


RUNNABLE_CAMPAIGN_STATUSES = {CampaignStatus.DRAFT, CampaignStatus.PAUSED}


class AgentRunService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.agent_runs = AgentRunRepository(session)
        self.campaigns = CampaignRepository(session)
        self.products = ProductRepository(session)

    def create(self, request: AgentRunCreate) -> AgentRunRead:
        campaign = CampaignRead.model_validate(self.campaigns.get(request.campaign_id))
        if campaign.status not in RUNNABLE_CAMPAIGN_STATUSES:
            raise ConflictError(
                "agent run can only be created for draft or paused campaigns",
                {"campaign_id": campaign.id, "status": campaign.status.value},
            )
        product = ProductRead.model_validate(self.products.get(campaign.product_id))
        objective = request.objective or self._default_objective(product, campaign)
        model = self.agent_runs.create(
            campaign_id=campaign.id,
            product_id=product.id,
            objective=objective,
            context_snapshot={
                "product": product.model_dump(mode="json"),
                "campaign": campaign.model_dump(mode="json"),
            },
            max_tool_calls=request.max_tool_calls,
            max_llm_calls=request.max_llm_calls,
            max_leads=request.max_leads or campaign.max_leads,
        )
        return AgentRunRead.model_validate(model)

    def list(self) -> list[AgentRunRead]:
        return [AgentRunRead.model_validate(model) for model in self.agent_runs.list()]

    def list_by_campaign(self, campaign_id: str) -> list[AgentRunRead]:
        self.campaigns.get(campaign_id)
        return [
            AgentRunRead.model_validate(model)
            for model in self.agent_runs.list_by_campaign(campaign_id)
        ]

    def get(self, run_id: str) -> AgentRunDetail:
        run = self.agent_runs.get(run_id)
        detail = AgentRunDetail.model_validate(run)
        detail.steps = [AgentStepRead.model_validate(model) for model in self.agent_runs.list_steps(run_id)]
        detail.tool_calls = [
            ToolCallRead.model_validate(model) for model in self.agent_runs.list_tool_calls(run_id)
        ]
        return detail

    def cancel(self, run_id: str) -> AgentRunRead:
        return AgentRunRead.model_validate(self.agent_runs.cancel(run_id))

    def retry(self, run_id: str) -> AgentRunRead:
        return AgentRunRead.model_validate(self.agent_runs.retry(run_id))

    @staticmethod
    def _default_objective(product: ProductRead, campaign: CampaignRead) -> str:
        return (
            f"Validate {product.product_name} for {product.target_customer}. "
            f"Campaign mode: {campaign.goal_type.value}. "
            f"ICP preset: {campaign.icp_preset_id or 'default-web-validation'}. "
            f"Goal: {campaign.goal_override or product.validation_goal}. "
            f"Create human-approved outreach drafts only for qualified leads."
        )
