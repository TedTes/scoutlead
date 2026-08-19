from leads.schemas import LeadRead
from products.schemas import ProductRead


def response_prompt(product: ProductRead, lead: LeadRead, body: str) -> str:
    return "\n".join(
        [
            f"Product: {product.product_name}",
            f"Lead: {lead.company_name}",
            f"Inbound response: {body}",
        ]
    )
