from campaigns.schemas import OutreachChannel
from leads.schemas import LeadRead
from products.schemas import ProductRead


def outreach_sell_prompt(product: ProductRead, lead: LeadRead, channel: OutreachChannel) -> str:
    return "\n".join(
        [
            f"Channel: {channel.value}",
            "Campaign goal type: sell",
            "Write concise sales outreach. Tie a public signal to a concrete value proposition.",
            f"Product: {product.product_name}",
            f"Offer: {product.offer_summary or product.product_description or product.product_name}",
            f"Value proposition: {product.value_proposition or product.offer_summary or ''}",
            f"Outreach objective: {product.outreach_objective or 'Start a relevant sales conversation.'}",
            f"Constraints: {product.constraints}",
            f"Lead: {lead.model_dump(mode='json')}",
        ]
    )
