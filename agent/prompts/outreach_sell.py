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
            f"Value proposition: {product.value_proposition}",
            f"Outreach objective: {product.outreach_objective}",
            f"Constraints: {product.constraints}",
            f"Lead: {lead.model_dump(mode='json')}",
        ]
    )
