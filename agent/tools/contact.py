from __future__ import annotations

import re
from typing import Any

from leads.schemas import LeadRead
from tools.base import ToolResult, ToolSlot, measured_tool_result

_OWNER_TERMS = ("owner", "founder", "ceo", "president", "principal", "proprietor")
_ROLE_TERMS = ("contact", "hello", "info", "office", "team")
_LOW_PRIORITY_TERMS = ("sales", "support", "admin", "help", "service", "noreply", "no-reply", "billing")
_NAME_PATTERN = re.compile(r"^[a-z]{2,}[._-][a-z]{2,}$")


def _local_part(email: str) -> str:
    return email.split("@", 1)[0].lower()


def _rank_candidate(email: str) -> int:
    """Score how likely an email is to reach an actual decision-maker, not just an inbox."""
    local = _local_part(email)
    if any(term in local for term in _OWNER_TERMS):
        return 88
    if any(term in local for term in _LOW_PRIORITY_TERMS):
        return 40
    if any(term in local for term in _ROLE_TERMS):
        return 58
    if _NAME_PATTERN.match(local):
        return 72
    return 45


class PublicEmailContactTool:
    """Resolves an org's public website evidence into the most reachable contact.

    This is the Contact slot's resolution step: it does not simply echo the
    Research step's LLM-extracted email. Research gathers raw evidence
    (`contact_candidates`, scraped independently from the site's HTML); this
    tool applies deterministic, code-owned ranking over that evidence to pick
    the candidate most likely to reach an actual owner/decision-maker.
    """

    name = "public_email"
    slot = ToolSlot.CONTACT

    def run(self, context: dict[str, Any]) -> ToolResult:
        lead = LeadRead.model_validate(context["lead"])

        candidates = list(lead.research.contact_candidates) if lead.research else []
        if not candidates:
            fallback = lead.contact_email or (lead.research.contact_email if lead.research else None)
            candidates = [fallback] if fallback else []

        ranked = sorted(
            ((email, _rank_candidate(email)) for email in candidates),
            key=lambda pair: pair[1],
            reverse=True,
        )

        def action() -> dict[str, str] | None:
            if not ranked:
                return None
            email, _score = ranked[0]
            return {"email": email, "source": "contact_candidate_ranking"}

        source_urls = []
        if lead.website_url:
            source_urls.append(lead.website_url)
        if lead.research:
            source_urls.extend(lead.research.sources)

        return measured_tool_result(
            provider="website_inspection",
            slot=self.slot,
            confidence=ranked[0][1] if ranked else 0,
            source_urls=list(dict.fromkeys(source_urls)),
            action=action,
        )
