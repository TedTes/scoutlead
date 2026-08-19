from __future__ import annotations

from agents.llm import LLMClient
from campaigns.schemas import CampaignRead
from conversations.schemas import ConversationRead
from insights.schemas import CampaignInsightDraft
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
        )
