from __future__ import annotations

from sqlalchemy.orm import Session

from agents.llm import LLMClient
from leads.repository import LeadRepository
from leads.schemas import LeadRead, QualificationResult
from products.repository import ProductRepository
from products.schemas import ProductRead
from prompts.qualification import qualification_prompt
from workflows.qualification import enforce_qualification_boundary


class LeadQualificationService:
    def __init__(self, *, session: Session, llm: LLMClient) -> None:
        self.session = session
        self.llm = llm
        self.leads = LeadRepository(session)
        self.products = ProductRepository(session)

    def qualify(self, lead_id: str) -> LeadRead:
        lead = LeadRead.model_validate(self.leads.get(lead_id))
        product = ProductRead.model_validate(self.products.get(lead.product_id))
        result = self.llm.generate_object(
            task="lead_qualification",
            system="Score the lead against explicit qualification criteria.",
            prompt=qualification_prompt(product, lead),
            response_model=QualificationResult,
            context={
                "product": product.model_dump(mode="json"),
                "lead": lead.model_dump(mode="json"),
            },
        )
        result = enforce_qualification_boundary(product, lead, result)
        return LeadRead.model_validate(self.leads.attach_qualification(lead.id, result))
