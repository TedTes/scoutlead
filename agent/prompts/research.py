from leads.schemas import LeadRead
from products.schemas import ProductRead
from tools.browser import WebsiteInspection


def research_prompt(product: ProductRead, lead: LeadRead, inspection: WebsiteInspection | None) -> str:
    return "\n".join(
        [
            "Classify this search result as a potential customer only if it appears to be an organization that could buy or use the product for itself.",
            "Do not treat product vendors, competitor/alternative products, software/tool category pages, blogs, articles, directories, or review pages as potential customers.",
            "If the result is not a target customer, set lead_type accordingly and add a clear disqualifier explaining why.",
            "lead_type must be one of: target_customer, competitor_or_alternative, vendor_to_target_customer, content_or_directory, irrelevant, unknown.",
            "Use public evidence only. Do not infer buyer fit from matching keywords alone.",
            f"Product: {product.product_name}",
            f"Product description: {product.product_description}",
            f"Target customer: {product.target_customer}",
            f"Problem being solved: {product.problem_being_solved}",
            f"Target geography: {product.target_geography}",
            f"Lead: {lead.company_name}",
            f"Known description: {lead.description or ''}",
            f"Raw search sources: {lead.raw_sources}",
            f"Website title: {inspection.title if inspection else ''}",
            f"Website description: {inspection.description if inspection else ''}",
            f"Website text: {inspection.text if inspection else ''}",
        ]
    )
