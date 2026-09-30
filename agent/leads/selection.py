from __future__ import annotations

from typing import Any

from campaigns.schemas import CampaignRead
from evaluation.digital_opportunity import (
    has_minimum_opportunity,
    opportunity_score_from_sources,
)
from leads.schemas import ContactVerificationStatus, LeadRead


def select_campaign_results(
    campaign: CampaignRead,
    leads: list[LeadRead],
) -> list[LeadRead]:
    """Apply a run's delivery policy without deleting its underlying evidence."""
    source_inputs = campaign.source_inputs or {}
    if not source_inputs.get("requires_digital_opportunity"):
        return leads

    eligible = [
        lead
        for lead in leads
        if has_minimum_opportunity(lead.raw_sources, minimum="moderate")
    ]
    eligible.sort(key=_opportunity_rank, reverse=True)
    limit = _positive_int(source_inputs.get("requested_result_count")) or campaign.max_leads
    return eligible[:limit]


def _opportunity_rank(lead: LeadRead) -> tuple[int, int, float, float]:
    qualification_score = float(lead.qualification.score if lead.qualification else 0)
    return (
        opportunity_score_from_sources(lead.raw_sources),
        _contact_readiness(lead),
        lead.rank_score if lead.rank_score is not None else qualification_score,
        lead.created_at.timestamp(),
    )


def _contact_readiness(lead: LeadRead) -> int:
    score = 0
    if lead.contact_email:
        score += 40
    if lead.verification_status == ContactVerificationStatus.VALID:
        score += 40
    elif lead.verification_status == ContactVerificationStatus.RISKY:
        score += 10
    elif lead.verification_status == ContactVerificationStatus.INVALID:
        score -= 40
    if _raw_value(lead.raw_sources, {"phone", "contact_phone", "telephone", "nationalphonenumber"}):
        score += 20
    return score


def _raw_value(sources: list[dict[str, Any]], keys: set[str]) -> str | None:
    stack: list[Any] = list(sources)
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key, item in value.items():
                if key.casefold() in keys and isinstance(item, str) and item.strip():
                    return item.strip()
                stack.append(item)
        elif isinstance(value, list):
            stack.extend(value)
    return None


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
