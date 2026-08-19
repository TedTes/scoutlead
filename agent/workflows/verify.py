from __future__ import annotations

from typing import Any, Callable

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus
from icp.schemas import SlotConfig
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadStatus
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from orchestration.confidence import downgrade_contact_confidence
from orchestration.slot_runner import SlotRunner
from products.schemas import ProductRead
from tools.base import ToolExecutionMode, ToolSlot
from tools.verify import EmailSyntaxVerifyTool


class VerifyWorkflow:
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
            slot=ToolSlot.VERIFY,
            mode=ToolExecutionMode.FIRST_GOOD,
            tools=[],
            confidence_threshold=70,
            target_count=1,
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
        tools = [EmailSyntaxVerifyTool()]
        for lead_model in self.leads.list_by_campaign(campaign.id):
            lead = LeadRead.model_validate(lead_model)
            if lead.status != LeadStatus.RESEARCHED:
                continue
            email = lead.contact_email or (lead.research.contact_email if lead.research else None)
            if not email:
                processed.append(lead)
                continue
            result = runner.run(
                config=self.slot_config,
                context={"email": email, "lead": lead.model_dump(mode="json")},
                tools=tools,
                on_tool_start=self.on_tool_start,
                on_tool_success=self.on_tool_success,
                on_tool_error=self.on_tool_error,
            )
            verdict = "invalid"
            confidence = 20
            if result.accepted and isinstance(result.data[0], dict):
                verdict = str(result.data[0].get("verdict") or "unknown")
                confidence = result.accepted[0].confidence
            elif result.rejected:
                rejected_data = result.rejected[0].data
                if isinstance(rejected_data, dict):
                    verdict = str(rejected_data.get("verdict") or "unknown")
                confidence = result.rejected[0].confidence
            if lead.research:
                contact_confidence = downgrade_contact_confidence(
                    lead, verdict=verdict, confidence=confidence
                )
                research = lead.research.model_copy(
                    update={
                        "confidence": contact_confidence["confidence"],
                        "disqualifiers": [
                            *lead.research.disqualifiers,
                            *([] if verdict == "valid" else [f"email_verification_{verdict}"]),
                        ],
                    }
                )
                processed.append(LeadRead.model_validate(self.leads.attach_research(lead.id, research)))
            else:
                processed.append(lead)

        self.memory.create_observation(
            CampaignMemoryCreate(
                product_id=product.id,
                campaign_id=campaign.id,
                type=ObservationType.LEAD_QUALITY,
                content=f"Verify slot processed {len(processed)} researched leads.",
                tags=["verify", "first_good"],
            )
        )
        return processed
