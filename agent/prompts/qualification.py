from leads.schemas import CriterionScore, LeadRead, LeadFitType, QualificationResult
from products.schemas import ProductRead


def qualification_prompt(product: ProductRead, lead: LeadRead) -> str:
    return "\n".join(
        [
            "Decide whether this lead should receive outreach.",
            "Qualified must be false if the lead is not a likely buyer/user matching the target customer.",
            "Qualified must be false for competitors, alternative products, vendors selling tools to the ICP, content pages, directories, or review pages.",
            "Qualified must be false if public evidence is too weak or if the lead has disqualifiers.",
            "Use a 0-100 score. Scores below 65 are not qualified.",
            f"Product: {product.product_name}",
            f"Target customer: {product.target_customer}",
            f"Qualification criteria: {product.qualification_criteria}",
            f"Lead research: {lead.research}",
        ]
    )


def disqualified_by_research(
    product: ProductRead,
    lead: LeadRead,
    *,
    reason: str | None = None,
    score: int | None = None,
) -> QualificationResult:
    disqualifiers = lead.research.disqualifiers if lead.research else []
    rationale = reason or (
        "Lead was disqualified before outreach because public research identified: "
        + ", ".join(disqualifiers)
    )
    return QualificationResult(
        qualified=False,
        score=score if score is not None else min(25, lead.research.confidence if lead.research else 0),
        rationale=rationale,
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


DISQUALIFYING_LEAD_TYPES = {
    LeadFitType.COMPETITOR_OR_ALTERNATIVE,
    LeadFitType.VENDOR_TO_TARGET_CUSTOMER,
    LeadFitType.CONTENT_OR_DIRECTORY,
    LeadFitType.IRRELEVANT,
}
