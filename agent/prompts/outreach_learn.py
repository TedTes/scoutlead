from campaigns.schemas import OutreachChannel
from leads.schemas import LeadRead
from messages.schemas import OutreachDraft
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


def fallback_outreach_learn(
    product: ProductRead, lead: LeadRead, channel: OutreachChannel
) -> OutreachDraft:
    evidence = lead.research.signals[0] if lead.research and lead.research.signals else lead.company_name
    return OutreachDraft(
        channel=channel,
        subject=f"Question about {lead.company_name}",
        body="\n".join(
            [
                "Hi there,",
                "",
                f"I am validating a workflow around this problem: {product.problem_being_solved}",
                f"I noticed {lead.company_name} because of this signal: {evidence}.",
                "",
                "I am not trying to pitch cold here. I am trying to understand whether this pain is real and how teams handle it today.",
                "",
                f"{product.outreach_objective} Would you be open to a short customer-discovery conversation?",
                "",
                "Thanks,",
            ]
        ),
        personalization_notes=[f"Referenced signal: {evidence}", "Framed as customer discovery."],
        approach_tag="learn_customer_discovery",
    )
