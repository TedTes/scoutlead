from __future__ import annotations

from typing import Any

from leads.schemas import AgentFitStatus, LeadRead, LeadReviewStatus, QualificationResult


MAYBE_FIT_SCORE = 50


def normalize_agent_fit_status(result: QualificationResult) -> AgentFitStatus:
    if result.fit_status:
        return result.fit_status
    if result.qualified:
        return AgentFitStatus.GOOD_FIT
    if result.score >= MAYBE_FIT_SCORE and "do not" not in result.recommended_next_step.lower():
        return AgentFitStatus.MAYBE
    return AgentFitStatus.NOT_FIT


def normalize_qualification_result(result: QualificationResult) -> QualificationResult:
    return result.model_copy(update={"fit_status": normalize_agent_fit_status(result)})


def can_shortlist_lead(
    *,
    review_status: LeadReviewStatus | str | None,
    qualification: QualificationResult | dict[str, Any] | None,
) -> bool:
    status = _review_status(review_status)
    if status == LeadReviewStatus.NOT_FIT:
        return False
    if status in {LeadReviewStatus.GOOD_FIT, LeadReviewStatus.MAYBE}:
        return True
    fit_status = _qualification_fit_status(qualification)
    return fit_status in {AgentFitStatus.GOOD_FIT, AgentFitStatus.MAYBE}


def is_outreach_ready(lead: LeadRead) -> bool:
    return bool(
        lead.shortlisted_at
        and can_shortlist_lead(
            review_status=lead.review_status,
            qualification=lead.qualification,
        )
    )


def _review_status(value: LeadReviewStatus | str | None) -> LeadReviewStatus:
    if isinstance(value, LeadReviewStatus):
        return value
    if isinstance(value, str) and value:
        return LeadReviewStatus(value)
    return LeadReviewStatus.UNREVIEWED


def _qualification_fit_status(
    qualification: QualificationResult | dict[str, Any] | None,
) -> AgentFitStatus | None:
    if qualification is None:
        return None
    result = (
        qualification
        if isinstance(qualification, QualificationResult)
        else QualificationResult.model_validate(qualification)
    )
    return normalize_agent_fit_status(result)
