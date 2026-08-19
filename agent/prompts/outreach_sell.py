from campaigns.schemas import OutreachChannel
from leads.schemas import LeadRead
from messages.schemas import OutreachDraft
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


def fallback_outreach_sell(
    product: ProductRead, lead: LeadRead, channel: OutreachChannel
) -> OutreachDraft:
    evidence = lead.research.signals[0] if lead.research and lead.research.signals else lead.company_name
    return OutreachDraft(
        channel=channel,
        subject=f"{product.product_name} for {lead.company_name}",
        body="\n".join(
            [
                "Hi there,",
                "",
                f"I noticed {lead.company_name} because of this signal: {evidence}.",
                "",
                product.value_proposition,
                "",
                f"{product.outreach_objective} Would it be worth a quick look?",
                "",
                "Thanks,",
            ]
        ),
        personalization_notes=[f"Referenced signal: {evidence}", "Framed as product interest."],
        approach_tag="sell_value_signal",
    )
