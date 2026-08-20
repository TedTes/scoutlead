from __future__ import annotations

from typing import Any, Callable

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus
from icp.schemas import SlotConfig
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadStatus
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from orchestration.slot_runner import SlotRunner
from products.schemas import ProductRead
from tools.base import ToolExecutionMode, ToolSlot
from tools.registry import resolve_tools


class SignalWorkflow:
    def __init__(
        self,
        *,
        campaigns: CampaignRepository,
        leads: LeadRepository,
        memory: MemoryRepository,
        slot_config: SlotConfig | None = None,
        on_tool_start: Callable[[str, dict[str, Any], str], str | None] | None = None,
        on_tool_success: Callable[[str, object], None] | None = None,
        on_tool_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        self.campaigns = campaigns
        self.leads = leads
        self.memory = memory
        self.slot_config = slot_config or SlotConfig(
            slot=ToolSlot.SIGNAL,
            mode=ToolExecutionMode.ACCUMULATE,
            tools=[],
            confidence_threshold=55,
            target_count=5,
        )
        self.on_tool_start = on_tool_start
        self.on_tool_success = on_tool_success
        self.on_tool_error = on_tool_error

    def run(self, product: ProductRead, campaign: CampaignRead) -> list[LeadRead]:
        self.campaigns.update_status(
            campaign.id, CampaignStatus.RESEARCHING, stage=CampaignStage.RESEARCH
        )
        processed: list[LeadRead] = []
        runner = SlotRunner()
        tools = resolve_tools(self.slot_config)
        for lead_model in self.leads.list_by_campaign(campaign.id):
            lead = LeadRead.model_validate(lead_model)
            if lead.status != LeadStatus.RESEARCHED:
                continue
            result = runner.run(
                config=self.slot_config,
                context={"product": product.model_dump(mode="json"), "lead": lead.model_dump(mode="json")},
                tools=tools,
                on_tool_start=self.on_tool_start,
                on_tool_success=self.on_tool_success,
                on_tool_error=self.on_tool_error,
            )
            if lead.research and result.data:
                values = [
                    str(row.get("value")) for row in result.data if isinstance(row, dict) and row.get("value")
                ]
                research = lead.research.model_copy(
                    update={"signals": list(dict.fromkeys([*lead.research.signals, *values]))}
                )
                processed.append(LeadRead.model_validate(self.leads.attach_research(lead.id, research)))
            else:
                processed.append(lead)

        self.memory.create_observation(
            CampaignMemoryCreate(
                product_id=product.id,
                campaign_id=campaign.id,
                type=ObservationType.LEAD_QUALITY,
                content=f"Signal slot processed {len(processed)} researched leads.",
                tags=["signal", "accumulate"],
            )
        )
        return processed
