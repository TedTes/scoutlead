import csv
from io import StringIO

from leads.schemas import LeadRead
from leads.policy import best_contact_channel
from evaluation.digital_opportunity import opportunity_evidence_from_sources


EXPORT_COLUMNS = [
    "business",
    "category",
    "address",
    "phone",
    "email",
    "email_verified",
    "website",
    "fit_status",
    "fit_score",
    "opportunity_level",
    "opportunity_score",
    "opportunity_evidence",
    "evidence_1",
    "evidence_2",
    "evidence_3",
    "best_channel",
    "opener",
    "talk_track",
    "scoutlead_url",
]


def leads_csv(leads: list[LeadRead], *, scoutlead_path: str) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for lead in leads:
        writer.writerow(_row(lead, scoutlead_path=scoutlead_path))
    return output.getvalue()


def _row(lead: LeadRead, *, scoutlead_path: str) -> dict[str, object]:
    qualification = lead.qualification
    evidence = list(qualification.positive_signals if qualification else [])[:3]
    evidence.extend([""] * (3 - len(evidence)))
    channel, _ = best_contact_channel(lead)
    approach = lead.approach
    opportunity = opportunity_evidence_from_sources(lead.raw_sources) or {}
    opportunity_signals = opportunity.get("signals")
    if not isinstance(opportunity_signals, list):
        opportunity_signals = []
    return {
        "business": lead.company_name,
        "category": lead.research.business_type if lead.research else "",
        "address": _raw_value(lead, {"address", "formatted_address", "street_address"}) or lead.geography or "",
        "phone": _raw_value(lead, {"phone", "contact_phone", "telephone"}) or "",
        "email": lead.contact_email or "",
        "email_verified": lead.verification_status.value == "valid",
        "website": lead.website_url or "",
        "fit_status": qualification.fit_status.value if qualification and qualification.fit_status else "",
        "fit_score": qualification.score if qualification else "",
        "opportunity_level": opportunity.get("level") or "",
        "opportunity_score": opportunity.get("score") if opportunity else "",
        "opportunity_evidence": " | ".join(
            str(signal.get("message") or signal.get("key") or "").strip()
            for signal in opportunity_signals
            if isinstance(signal, dict) and (signal.get("message") or signal.get("key"))
        ),
        "evidence_1": evidence[0],
        "evidence_2": evidence[1],
        "evidence_3": evidence[2],
        "best_channel": approach.best_channel.value if approach else channel.value,
        "opener": approach.opener if approach else "",
        "talk_track": " | ".join(approach.talk_track) if approach else "",
        "scoutlead_url": f"{scoutlead_path}#lead={lead.id}",
    }


def _raw_value(lead: LeadRead, keys: set[str]) -> str | None:
    stack: list[object] = list(lead.raw_sources)
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
