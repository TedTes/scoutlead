from __future__ import annotations

from typing import Any

from leads.schemas import (
    AgentFitStatus,
    BestChannel,
    ContactPolicyStatus,
    ContactVerificationStatus,
    LeadRead,
    LeadReviewStatus,
    QualificationResult,
)
from suppressions.repository import is_blocked_contact_policy


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


def controlled_signal_tags(tags: list[str], vocabulary: list[str] | None) -> list[str]:
    if not vocabulary:
        return []
    canonical = {tag.strip().casefold(): tag.strip() for tag in vocabulary if tag.strip()}
    return list(
        dict.fromkeys(
            canonical[tag.strip().casefold()]
            for tag in tags
            if tag.strip().casefold() in canonical
        )
    )


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
        and not is_contact_blocked_lead(lead)
        and can_shortlist_lead(
            review_status=lead.review_status,
            qualification=lead.qualification,
        )
    )


def lead_email(lead: LeadRead) -> str | None:
    if lead.contact_email:
        return lead.contact_email
    if lead.research and lead.research.contact_email:
        return lead.research.contact_email
    return None


def is_reachable_lead(lead: LeadRead) -> bool:
    return bool(
        lead_email(lead)
        and not is_contact_blocked_lead(lead)
        and lead.verification_status != ContactVerificationStatus.INVALID
    )


def is_verified_lead(lead: LeadRead) -> bool:
    return lead.verification_status == ContactVerificationStatus.VALID


def is_draftable_lead(lead: LeadRead) -> bool:
    return is_outreach_ready(lead) and is_reachable_lead(lead) and is_verified_lead(lead)


def is_contact_blocked_lead(lead: LeadRead) -> bool:
    return is_blocked_contact_policy(lead.contact_policy_status)


def contact_block_reason(lead: LeadRead) -> str:
    status = lead.contact_policy_status
    if isinstance(status, ContactPolicyStatus):
        label = status.value.replace("_", " ")
    else:
        label = str(status or "blocked").replace("_", " ")
    return lead.contact_policy_reason or f"Contact policy is {label}."


def best_contact_channel(lead: LeadRead) -> tuple[BestChannel, str]:
    if lead.contact_email and lead.verification_status == ContactVerificationStatus.VALID:
        return BestChannel.EMAIL, "A verified email is available."
    if _raw_value(lead.raw_sources, {"phone", "contact_phone", "telephone"}):
        return BestChannel.PHONE, "A public phone number is available."
    signals = [*(lead.research.signals if lead.research else [])]
    if any("contact form" in signal.casefold() for signal in signals) or _raw_truthy(
        lead.raw_sources,
        {"has_contact_form", "contact_form"},
    ):
        return BestChannel.CONTACT_FORM, "The business website has a contact form."
    if _raw_value(lead.raw_sources, {"address", "street_address", "formatted_address"}):
        return BestChannel.VISIT, "A public business address is available."
    return BestChannel.NONE, "No verified outreach channel is available."


def _raw_value(sources: list[dict], keys: set[str]) -> str | None:
    for source in sources:
        for key, value in _walk_items(source):
            if key.casefold() in keys and isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _raw_truthy(sources: list[dict], keys: set[str]) -> bool:
    return any(
        key.casefold() in keys and bool(value)
        for source in sources
        for key, value in _walk_items(source)
    )


def _walk_items(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk_items(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_items(item)


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
