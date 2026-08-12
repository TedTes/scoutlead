from evaluation.schemas import LeadQualityEvaluation
from leads.schemas import LeadRead


def evaluate_lead_quality(lead: LeadRead) -> LeadQualityEvaluation:
    score = lead.qualification.score if lead.qualification else lead.research.confidence if lead.research else 0
    fit = "high" if score >= 75 else "medium" if score >= 50 else "low"
    reasons = []
    if lead.qualification:
        for criterion in lead.qualification.criteria:
            reasons.extend(criterion.evidence)
    if lead.research:
        reasons.extend(lead.research.signals)
    return LeadQualityEvaluation(lead_id=lead.id, score=score, fit=fit, reasons=reasons[:5])
