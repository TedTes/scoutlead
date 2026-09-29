from leads.schemas import BestChannel, LeadRead
from products.schemas import ProductRead


def approach_prompt(
    product: ProductRead,
    lead: LeadRead,
    *,
    channel: BestChannel,
) -> str:
    evidence = {
        "description": lead.description,
        "research": lead.research.model_dump(mode="json") if lead.research else None,
        "qualification": (
            lead.qualification.model_dump(mode="json") if lead.qualification else None
        ),
        "raw_sources": lead.raw_sources[:3],
    }
    return "\n".join(
        [
            "Write a concise evidence-grounded first approach to this business.",
            f"Channel: {channel.value}.",
            "Return an opener of at most two sentences.",
            "For phone or visit, return exactly three short talk-track bullets; otherwise return up to three.",
            "Reference at least one evidence item and list the exact evidence references used.",
            "Do not make claims beyond the supplied evidence.",
            "Do not imply the business has a problem unless the evidence explicitly supports it.",
            f"Offer: {product.offer_summary or product.product_description or product.product_name}",
            f"Target customer: {product.target_customer}",
            f"Business: {lead.company_name}",
            f"Evidence: {evidence}",
        ]
    )
