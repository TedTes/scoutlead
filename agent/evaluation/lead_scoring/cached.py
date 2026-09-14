from __future__ import annotations

from typing import Any

from evaluation.lead_scoring.policies import (
    disqualifiers,
    final_fit_score,
    fit_status,
    missing_evidence,
    qualification_rationale,
    score_breakdown,
)
from evaluation.lead_scoring.signals import (
    cached_business_type,
    cached_signals,
    cached_sources,
)
from leads.schemas import AgentFitStatus, CriterionScore, LeadFitType, LeadRead, LeadResearch, QualificationResult
from products.schemas import ProductRead
from shared.utils import truncate


def build_cached_lead_research(
    *,
    product: ProductRead,
    lead: LeadRead,
    row: dict[str, Any],
    confidence: int,
) -> LeadResearch:
    signals = cached_signals(row=row, lead=lead)
    summary = truncate(
        lead.description
        or f"{lead.company_name} matched cached business-pool evidence for {product.product_name}.",
        700,
    )
    return LeadResearch(
        summary=summary,
        lead_type=LeadFitType.TARGET_CUSTOMER,
        business_type=cached_business_type(product=product, row=row, lead=lead),
        geography=lead.geography,
        website_url=lead.website_url,
        contact_email=lead.contact_email,
        contact_candidates=[lead.contact_email] if lead.contact_email else [],
        signals=signals,
        pain_indicators=[],
        disqualifiers=[],
        sources=cached_sources(row=row, lead=lead),
        confidence=max(0, min(100, confidence)),
    )


def score_cached_lead(
    *,
    product: ProductRead,
    lead: LeadRead,
    row: dict[str, Any],
    confidence: int,
) -> QualificationResult:
    del confidence
    signals = cached_signals(row=row, lead=lead)
    breakdown = score_breakdown(product=product, row=row, lead=lead)
    risks = disqualifiers(product=product, row=row, lead=lead)
    score = final_fit_score(score_breakdown=breakdown, disqualifiers=risks)
    status = fit_status(score_breakdown=breakdown, disqualifiers=risks)
    qualified = status in {AgentFitStatus.GOOD_FIT, AgentFitStatus.MAYBE}
    missing = missing_evidence(product=product, row=row, lead=lead, score_breakdown=breakdown)
    return QualificationResult(
        qualified=qualified,
        fit_status=status,
        score=score,
        score_breakdown=breakdown,
        rationale=qualification_rationale(
            product=product,
            lead=lead,
            score_breakdown=breakdown,
            disqualifiers=risks,
        ),
        positive_signals=signals[:6],
        missing_evidence=missing,
        risks=risks,
        criteria=[
            CriterionScore(
                criterion_id=criterion.id or criterion.label,
                label=criterion.label,
                score=breakdown.fit_score,
                evidence=signals[:3],
                missing_evidence=missing[:2],
            )
            for criterion in product.qualification_criteria
        ],
        recommended_next_step=(
            "Review the contact and shortlist manually before outreach."
            if qualified
            else "Review manually before taking action."
        ),
    )
