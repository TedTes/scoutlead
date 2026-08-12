from leads.schemas import LeadRead, LeadResearch
from products.schemas import ProductRead
from shared.utils import keyword_hits
from tools.browser import WebsiteInspection


def research_prompt(product: ProductRead, lead: LeadRead, inspection: WebsiteInspection | None) -> str:
    return "\n".join(
        [
            f"Product: {product.product_name}",
            f"Target customer: {product.target_customer}",
            f"Target geography: {product.target_geography}",
            f"Lead: {lead.company_name}",
            f"Known description: {lead.description or ''}",
            f"Website title: {inspection.title if inspection else ''}",
            f"Website description: {inspection.description if inspection else ''}",
            f"Website text: {inspection.text if inspection else ''}",
        ]
    )


def fallback_research(product: ProductRead, lead: LeadRead, inspection: WebsiteInspection | None) -> LeadResearch:
    combined = " ".join(
        [
            lead.company_name,
            lead.description or "",
            inspection.title if inspection and inspection.title else "",
            inspection.description if inspection and inspection.description else "",
            inspection.text if inspection else "",
        ]
    )
    criteria = [criterion.label for criterion in product.qualification_criteria]
    signals = keyword_hits(combined, [product.target_customer, *criteria])
    email = lead.contact_email or (inspection.emails[0] if inspection and inspection.emails else None)
    confidence = 70 if signals and email else 55 if signals else 35
    return LeadResearch(
        summary=lead.description or (inspection.description if inspection else None) or lead.company_name,
        business_type=signals[0] if signals else product.target_customer,
        geography=lead.geography or product.target_geography,
        website_url=lead.website_url or (inspection.url if inspection else None),
        contact_email=email,
        signals=signals or ["Needs manual review for target-customer fit."],
        pain_indicators=keyword_hits(combined, product.problem_being_solved.split()),
        disqualifiers=[],
        sources=[value for value in [lead.source, lead.website_url] if value],
        confidence=confidence,
    )
