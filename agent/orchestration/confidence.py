from __future__ import annotations

from typing import Any

from leads.schemas import LeadRead


def result_identity(value: Any) -> str:
    if isinstance(value, dict):
        return str(
            value.get("website_url")
            or value.get("url")
            or value.get("contact_email")
            or value.get("email")
            or value.get("company_name")
            or value.get("title")
            or value
        ).strip().lower()
    return str(value).strip().lower()


def dedupe_results(rows: list[Any]) -> list[Any]:
    seen: set[str] = set()
    unique: list[Any] = []
    for row in rows:
        identity = result_identity(row)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(row)
    return unique


def downgrade_contact_confidence(
    lead: LeadRead,
    *,
    verdict: str,
    confidence: int,
) -> dict[str, Any]:
    current_confidence = lead.research.confidence if lead.research else 0
    if verdict == "valid":
        updated_confidence = max(current_confidence, confidence)
    elif verdict in {"risky", "unknown"}:
        updated_confidence = min(current_confidence, confidence)
    else:
        updated_confidence = min(current_confidence, 20)
    return {
        "contact_email": lead.contact_email,
        "verification_verdict": verdict,
        "confidence": updated_confidence,
    }
