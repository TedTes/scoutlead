from __future__ import annotations

from collections import Counter

from agents.llm import LLMClient
from campaigns.schemas import CampaignRead
from conversations.schemas import ConversationRead, ResponseIntent
from insights.schemas import CampaignInsightDraft, Finding, IcpVerdict, IcpVerdictValue
from leads.schemas import LeadRead
from messages.schemas import MessageRead
from products.schemas import ProductRead
from prompts.insight_synthesis import insight_synthesis_prompt


class InsightSynthesizer:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def synthesize(
        self,
        *,
        product: ProductRead,
        campaign: CampaignRead,
        leads: list[LeadRead],
        messages: list[MessageRead],
        conversations: list[ConversationRead],
        metrics: dict,
    ) -> CampaignInsightDraft:
        fallback = fallback_insight(
            product=product,
            campaign=campaign,
            leads=leads,
            conversations=conversations,
            metrics=metrics,
        )
        return self.llm.generate_object(
            task="campaign_insight_synthesis",
            system="Synthesize concise, evidence-grounded campaign validation insights.",
            prompt=insight_synthesis_prompt(
                product=product,
                campaign=campaign,
                leads=leads,
                messages=messages,
                conversations=conversations,
                metrics=metrics,
            ),
            response_model=CampaignInsightDraft,
            context={
                "product": product.model_dump(mode="json"),
                "campaign": campaign.model_dump(mode="json"),
                "metrics": metrics,
            },
            fallback=fallback,
        )


def fallback_insight(
    *,
    product: ProductRead,
    campaign: CampaignRead,
    leads: list[LeadRead],
    conversations: list[ConversationRead],
    metrics: dict,
) -> CampaignInsightDraft:
    qualified = int(metrics.get("qualified_lead_count") or 0)
    lead_count = int(metrics.get("lead_count") or 0)
    response_count = int(metrics.get("response_count") or 0)
    interview_count = int(metrics.get("interview_request_count") or 0)
    disqualifiers = Counter(
        disqualifier
        for lead in leads
        for disqualifier in (lead.research.disqualifiers if lead.research else [])
    )
    inbound_intents = Counter(
        event.classification.intent.value
        for conversation in conversations
        for event in conversation.events
        if event.direction == "inbound" and event.classification
    )

    findings: list[Finding] = []
    if lead_count:
        findings.append(
            Finding(
                theme="Lead fit",
                summary=f"{qualified} of {lead_count} discovered leads qualified for outreach.",
                evidence=[
                    f"{lead.company_name}: {lead.qualification.rationale}"
                    for lead in leads
                    if lead.qualification
                ][:5],
                count=lead_count,
                confidence=70 if lead_count >= 5 else 45,
            )
        )
    if disqualifiers:
        findings.append(
            Finding(
                theme="Disqualification pattern",
                summary="Common disqualifiers: "
                + ", ".join(f"{name} ({count})" for name, count in disqualifiers.most_common(3)),
                evidence=[
                    f"{lead.company_name}: {', '.join(lead.research.disqualifiers)}"
                    for lead in leads
                    if lead.research and lead.research.disqualifiers
                ][:5],
                count=sum(disqualifiers.values()),
                confidence=75,
            )
        )
    if response_count:
        findings.append(
            Finding(
                theme="Response signal",
                summary="Inbound responses by intent: "
                + ", ".join(f"{intent} ({count})" for intent, count in inbound_intents.items()),
                evidence=[
                    event.body
                    for conversation in conversations
                    for event in conversation.events
                    if event.direction == "inbound"
                ][:5],
                count=response_count,
                confidence=80,
            )
        )

    if lead_count == 0:
        verdict = IcpVerdictValue.INSUFFICIENT_DATA
        rationale = "No leads have been collected yet."
        action = "Run discovery with a configured ICP preset and review source quality."
    elif interview_count > 0:
        verdict = IcpVerdictValue.STRONG
        rationale = "The campaign produced at least one interview request."
        action = "Continue the ICP test and collect more interview evidence."
    elif qualified / max(lead_count, 1) >= 0.4:
        verdict = IcpVerdictValue.MIXED
        rationale = "Discovery is finding some plausible leads, but response evidence is limited."
        action = "Tighten qualification signals and test another outreach angle."
    elif disqualifiers:
        verdict = IcpVerdictValue.WEAK
        rationale = "Discovery produced many non-customer or low-fit results."
        action = "Edit the ICP preset and discovery queries before sending more outreach."
    else:
        verdict = IcpVerdictValue.INSUFFICIENT_DATA
        rationale = "There is not enough conversation evidence to judge the ICP."
        action = "Run a larger discovery batch or add seed leads."

    return CampaignInsightDraft(
        summary=(
            f"{campaign.name} has {lead_count} leads, {qualified} qualified leads, "
            f"{response_count} responses, and {interview_count} interview requests."
        ),
        findings=findings,
        icp_verdict=IcpVerdict(verdict=verdict, rationale=rationale, recommended_action=action),
        evidence=[
            f"Product: {product.product_name}",
            f"Goal type: {campaign.goal_type.value}",
            f"North-star metric: {metrics.get('north_star_metric')}",
        ],
    )
