from campaigns.schemas import OutreachChannel
from leads.schemas import LeadRead
from products.schemas import ProductRead


def outreach_learn_prompt(product: ProductRead, lead: LeadRead, channel: OutreachChannel) -> str:
    return "\n".join(
        [
            f"Channel: {channel.value}",
            "Campaign goal type: learn",
            "Write customer-discovery outreach. Ask for perspective, not a sale.",
            f"Product: {product.product_name}",
            f"Problem being validated: {product.problem_being_solved}",
            f"Validation goal: {product.validation_goal}",
            f"Outreach objective: {product.outreach_objective}",
            f"Constraints: {product.constraints}",
            f"Lead: {lead.model_dump(mode='json')}",
        ]
    )
