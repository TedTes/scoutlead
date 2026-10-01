from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class OpportunityType(StrEnum):
    ANY = "any"
    MISSING_WEBSITE = "missing_website"
    MISSING_OR_UNAVAILABLE_WEBSITE = "missing_or_unavailable_website"


@dataclass(frozen=True)
class BusinessIndexSearch:
    niche_id: str
    market_key: str
    opportunity_type: OpportunityType
    evidence_fresh_after: datetime
    result_count: int

