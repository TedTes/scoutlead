from campaigns.schemas import OutreachChannel
from leads.schemas import LeadRead
from messages.schemas import OutreachDraft
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


def fallback_outreach(product: ProductRead, lead: LeadRead, channel: OutreachChannel) -> OutreachDraft:
    evidence = lead.research.signals[0] if lead.research and lead.research.signals else lead.company_name
    return OutreachDraft(
        channel=channel,
        subject=f"{product.product_name} question for {lead.company_name}",
        body="\n".join(
            [
                "Hi there,",
                "",
                f"I am validating {product.product_name}, {product.product_description}",
                f"I noticed {lead.company_name} because of this signal: {evidence}.",
                "",
                product.value_proposition,
                "",
                f"{product.outreach_objective} Would you be open to a short conversation?",
                "",
                "Thanks,",
            ]
        ),
        personalization_notes=[f"Referenced signal: {evidence}"],
        approach_tag="concise_validation_request",
    )
