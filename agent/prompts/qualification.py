from leads.schemas import CriterionScore, LeadRead, QualificationResult
from products.schemas import ProductRead
from shared.utils import keyword_hits


def qualification_prompt(product: ProductRead, lead: LeadRead) -> str:
    return "\n".join(
        [
            f"Product: {product.product_name}",
            f"Qualification criteria: {product.qualification_criteria}",
            f"Lead research: {lead.research}",
        ]
    )


def fallback_qualification(product: ProductRead, lead: LeadRead) -> QualificationResult:
    evidence_text = " ".join(
        [
            lead.company_name,
            lead.description or "",
            lead.research.summary if lead.research else "",
            " ".join(lead.research.signals if lead.research else []),
            " ".join(lead.research.pain_indicators if lead.research else []),
        ]
    )
    total_weight = sum(criterion.weight for criterion in product.qualification_criteria)
    earned_weight = 0.0
    required_miss = False
    scores: list[CriterionScore] = []

    for criterion in product.qualification_criteria:
        tokens = [token for token in criterion.label.split() if len(token) > 3]
        hits = keyword_hits(evidence_text, tokens)
        score = 100 if hits else 60 if lead.research and lead.research.confidence >= 60 else 25
        if score >= 60:
            earned_weight += criterion.weight * (score / 100)
        elif criterion.required:
            required_miss = True
        scores.append(
            CriterionScore(
                criterion_id=criterion.id or criterion.label,
                label=criterion.label,
                score=score,
                evidence=[f"Matched signal: {hit}" for hit in hits],
                missing_evidence=[] if hits else [f"No clear evidence for {criterion.label}"],
            )
        )

    score = round((earned_weight / total_weight) * 100) if total_weight else 0
    qualified = score >= 60 and not required_miss
    return QualificationResult(
        qualified=qualified,
        score=score,
        rationale=(
            "Lead appears to match enough qualification criteria for outreach."
            if qualified
            else "Lead needs stronger evidence or does not fit required criteria."
        ),
        criteria=scores,
        recommended_next_step=(
            "Draft validation outreach for human review." if qualified else "Do not send outreach."
        ),
    )
