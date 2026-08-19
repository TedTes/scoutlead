from campaigns.schemas import OutreachChannel
from leads.schemas import LeadRead
from products.schemas import ProductRead


def outreach_prompt(product: ProductRead, lead: LeadRead, channel: OutreachChannel) -> str:
    return "\n".join(
        [
            f"Channel: {channel.value}",
            f"Product: {product.product_name}",
            f"Value proposition: {product.value_proposition}",
            f"Validation goal: {product.validation_goal}",
            f"Outreach objective: {product.outreach_objective}",
            f"Constraints: {product.constraints}",
            f"Lead: {lead.model_dump(mode='json')}",
        ]
    )
