"""Reports how many leads in a campaign actually resolved to a usable contact.

This answers the one question that decides whether Contact is the bottleneck
for a given ICP: of the businesses that made it through research, what
fraction came out with a real email you could send to?

Usage:
    PYTHONPATH=agent python scripts/contact_yield.py <campaign_id>

Requires DATABASE_URL (and the rest of the .env) to point at the same database
the campaign was run against.
"""

from __future__ import annotations

import sys

from app.config import get_settings
from db.session import Database
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadStatus

RESEARCHED_OR_LATER = {
    LeadStatus.RESEARCHED,
    LeadStatus.QUALIFIED,
    LeadStatus.DISQUALIFIED,
    LeadStatus.OUTREACH_DRAFTED,
    LeadStatus.AWAITING_APPROVAL,
    LeadStatus.APPROVED,
    LeadStatus.SENT,
    LeadStatus.RESPONDED,
    LeadStatus.ARCHIVED,
}


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: PYTHONPATH=agent python scripts/contact_yield.py <campaign_id>")
        raise SystemExit(1)
    campaign_id = sys.argv[1]

    settings = get_settings()
    database = Database(settings.database_url)
    session = next(database.session())
    try:
        leads = [LeadRead.model_validate(model) for model in LeadRepository(session).list_by_campaign(campaign_id)]
    finally:
        session.close()

    if not leads:
        print(f"No leads found for campaign {campaign_id}.")
        return

    discovered = len(leads)
    researched = [lead for lead in leads if lead.status in RESEARCHED_OR_LATER]
    with_candidates = [lead for lead in researched if lead.research and lead.research.contact_candidates]
    with_resolved_email = [
        lead for lead in researched if (lead.contact_email or (lead.research and lead.research.contact_email))
    ]

    print(f"Campaign {campaign_id}")
    print(f"  discovered leads:                {discovered}")
    print(f"  reached research:                {len(researched)}")
    print(f"  had ANY scraped email candidate: {len(with_candidates)}  "
          f"({_pct(len(with_candidates), len(researched))} of researched)")
    print(f"  Contact resolved a usable email: {len(with_resolved_email)}  "
          f"({_pct(len(with_resolved_email), len(researched))} of researched)")
    print()
    print("  Businesses researched but with NO email anywhere on their site:")
    for lead in researched:
        if not (lead.research and lead.research.contact_candidates) and not lead.contact_email:
            print(f"    - {lead.company_name} ({lead.website_url or 'no website'})")


def _pct(part: int, total: int) -> str:
    if total == 0:
        return "n/a"
    return f"{round(100 * part / total)}%"


if __name__ == "__main__":
    main()
