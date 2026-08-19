from __future__ import annotations

from campaigns.schemas import CampaignRead
from conversations.schemas import ConversationRead
from leads.schemas import LeadRead
from messages.schemas import MessageRead
from products.schemas import ProductRead


def insight_synthesis_prompt(
    *,
    product: ProductRead,
    campaign: CampaignRead,
    leads: list[LeadRead],
    messages: list[MessageRead],
    conversations: list[ConversationRead],
    metrics: dict,
) -> str:
    return "\n".join(
        [
            "Synthesize campaign-level validation insights.",
            "Focus on what was learned about the ICP, pain, objections, and next experiment.",
            "Do not invent customer evidence. Use only supplied leads, messages, conversations, and metrics.",
            f"Product: {product.model_dump(mode='json')}",
            f"Campaign: {campaign.model_dump(mode='json')}",
            f"Metrics: {metrics}",
            f"Leads: {[lead.model_dump(mode='json') for lead in leads]}",
            f"Messages: {[message.model_dump(mode='json') for message in messages]}",
            f"Conversations: {[conversation.model_dump(mode='json') for conversation in conversations]}",
        ]
    )
