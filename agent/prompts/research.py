from leads.schemas import LeadRead
from products.schemas import ProductRead
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
