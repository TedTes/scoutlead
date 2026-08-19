from urllib.parse import urlparse

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
    disqualifiers = _disqualifiers(product, lead, combined)
    confidence = 70 if signals and email else 55 if signals else 35
    if disqualifiers:
        confidence = min(confidence, 35)
    return LeadResearch(
        summary=lead.description or (inspection.description if inspection else None) or lead.company_name,
        business_type=signals[0] if signals else product.target_customer,
        geography=lead.geography or product.target_geography,
        website_url=lead.website_url or (inspection.url if inspection else None),
        contact_email=email,
        signals=signals or ["Needs manual review for target-customer fit."],
        pain_indicators=keyword_hits(combined, product.problem_being_solved.split()),
        disqualifiers=disqualifiers,
        sources=[value for value in [lead.source, lead.website_url] if value],
        confidence=confidence,
    )


def _disqualifiers(product: ProductRead, lead: LeadRead, combined: str) -> list[str]:
    text = combined.lower()
    url = (lead.website_url or "").lower()
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    source_url = str(getattr(product, "source_url", "") or "").lower()
    disqualifiers: list[str] = []

    if source_url and parsed.netloc and parsed.netloc in urlparse(source_url).netloc.lower():
        disqualifiers.append("own_product_domain")

    content_or_directory_terms = (
        "best ",
        "top ",
        "review",
        "reviews",
        "comparison",
        "alternatives",
        "directory",
        "marketplace",
        "near me",
        "youtube",
        "watch?",
        "blog",
        "article",
        "guide",
        "template",
    )
    content_paths = (
        "/blog",
        "/article",
        "/reviews",
        "/review",
        "/compare",
        "/alternatives",
        "/directory",
        "/marketplace",
        "/watch",
        "/guide",
    )
    if any(term in text for term in content_or_directory_terms) or any(part in path for part in content_paths):
        disqualifiers.append("content_page_or_directory")

    return list(dict.fromkeys(disqualifiers))
