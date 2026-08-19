from leads.schemas import CriterionScore, LeadRead, QualificationResult
from products.schemas import ProductRead


def qualification_prompt(product: ProductRead, lead: LeadRead) -> str:
    return "\n".join(
        [
            f"Product: {product.product_name}",
            f"Qualification criteria: {product.qualification_criteria}",
            f"Lead research: {lead.research}",
        ]
    )


def disqualified_by_research(product: ProductRead, lead: LeadRead) -> QualificationResult:
    return QualificationResult(
        qualified=False,
        score=min(25, lead.research.confidence if lead.research else 0),
        rationale=(
            "Lead was disqualified before outreach because public research identified: "
            + ", ".join(lead.research.disqualifiers if lead.research else [])
        ),
        criteria=[
            CriterionScore(
                criterion_id=criterion.id or criterion.label,
                label=criterion.label,
                score=0,
                evidence=[],
                missing_evidence=["Lead has disqualifying public evidence."],
            )
            for criterion in product.qualification_criteria
        ],
        recommended_next_step="Do not send outreach.",
    )
