from __future__ import annotations

from typing import Any, Callable

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus
from icp.schemas import SlotConfig
from leads.repository import LeadRepository
from leads.schemas import ContactVerificationStatus, LeadRead, LeadStatus, LeadVerification
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from orchestration.confidence import downgrade_contact_confidence
from orchestration.slot_runner import SlotRunner
from products.schemas import ProductRead
from tools.base import ToolExecutionMode, ToolSlot
from tools.registry import resolve_tools
from tools.verify import EmailVerificationTool


class VerifyWorkflow:
    def __init__(
        self,
        *,
        campaigns: CampaignRepository,
        leads: LeadRepository,
        memory: MemoryRepository,
        slot_config: SlotConfig | None = None,
        verification_tool: EmailVerificationTool | None = None,
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
        self.verification_tool = verification_tool
        self.on_tool_start = on_tool_start
        self.on_tool_success = on_tool_success
        self.on_tool_error = on_tool_error

    def run(self, product: ProductRead, campaign: CampaignRead) -> list[LeadRead]:
        self.campaigns.update_status(
            campaign.id, CampaignStatus.RESEARCHING, stage=CampaignStage.RESEARCH
        )
        processed: list[LeadRead] = []
        runner = SlotRunner()
        tools = [self.verification_tool] if self.verification_tool else resolve_tools(self.slot_config)
        for lead_model in self.leads.list_by_campaign(campaign.id):
            lead = LeadRead.model_validate(lead_model)
            if lead.status != LeadStatus.RESEARCHED:
                continue
            email = lead.contact_email or (lead.research.contact_email if lead.research else None)
            if not email:
                updated = self.leads.attach_verification(
                    lead.id,
                    LeadVerification(
                        status=ContactVerificationStatus.UNKNOWN,
                        provider="system",
                        reason="No email address found.",
                        score=0,
                    ),
                )
                processed.append(LeadRead.model_validate(updated))
                continue
            result = runner.run(
                config=self.slot_config,
                context={
                    "email": email,
                    "phone": _lead_phone(lead),
                    "lead": lead.model_dump(mode="json"),
                },
                tools=tools,
                on_tool_start=self.on_tool_start,
                on_tool_success=self.on_tool_success,
                on_tool_error=self.on_tool_error,
            )
            verification = LeadVerification(
                status=ContactVerificationStatus.UNKNOWN,
                provider="system",
                reason="Verification did not return a usable result.",
                score=20,
            )
            if result.accepted:
                verification = _verification_from_tool_result(result.accepted[0])
            elif result.rejected:
                verification = _verification_from_tool_result(result.rejected[0])
            lead = LeadRead.model_validate(self.leads.attach_verification(lead.id, verification))
            if lead.research:
                contact_confidence = downgrade_contact_confidence(
                    lead, verdict=verification.status.value, confidence=verification.score
                )
                research = lead.research.model_copy(
                    update={
                        "confidence": contact_confidence["confidence"],
                        "disqualifiers": [
                            *lead.research.disqualifiers,
                            *(
                                []
                                if verification.status == ContactVerificationStatus.VALID
                                else [f"email_verification_{verification.status.value}"]
                            ),
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


def _verification_from_tool_result(result) -> LeadVerification:
    data = result.data if isinstance(result.data, dict) else {}
    raw_status = str(data.get("status") or data.get("verdict") or "unknown").lower()
    try:
        status = ContactVerificationStatus(raw_status)
    except ValueError:
        status = ContactVerificationStatus.UNKNOWN
    raw_score = data.get("score", result.confidence)
    try:
        score = int(raw_score)
    except (TypeError, ValueError):
        score = result.confidence
    return LeadVerification(
        status=status,
        provider=result.provider,
        reason=str(data.get("reason") or f"Verifier returned {status.value}."),
        score=max(0, min(100, score)),
    )


def _lead_phone(lead: LeadRead) -> str | None:
    phone_keys = {
        "normalized_contact_phone",
        "contact_phone",
        "nationalPhoneNumber",
        "internationalPhoneNumber",
        "phone",
        "phoneNumber",
        "phone_number",
        "telephone",
        "contactPhone",
        "sellerPhone",
        "ownerPhone",
    }
    for raw in lead.raw_sources:
        value = _phone_from_raw(raw, phone_keys)
        if value:
            return value
        nested = raw.get("raw") if isinstance(raw, dict) else None
        if isinstance(nested, dict):
            value = _phone_from_raw(nested, phone_keys)
            if value:
                return value
    return None


def _phone_from_raw(raw: dict, phone_keys: set[str]) -> str | None:
    for key in phone_keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return None
