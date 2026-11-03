from __future__ import annotations

from typing import Any


PAGE_SCOPED_NEGATIVE_SIGNALS = frozenset(
    {
        "contact_form_present",
        "quote_or_booking_form_present",
        "primary_cta_present",
        "click_to_call_present",
    }
)

PAGESPEED_GRADE_SIGNALS = frozenset(
    {
        "website_quality_score",
        "performance_score",
        "accessibility_score",
        "best_practices_score",
    }
)

_REQUIRED_SCOPE = {
    "contact_form_present": "contact_intent_page_complete",
    "quote_or_booking_form_present": "quote_intent_page_complete",
    "primary_cta_present": "homepage_complete",
    "click_to_call_present": "mobile_render_complete",
}


def pitch_scope_decision(
    signal_key: str,
    value: Any,
    payload: dict[str, Any],
) -> tuple[bool, str]:
    """Return whether one stored finding is specific enough to tell a prospect."""

    if signal_key == "website_status":
        if value == "missing":
            presence = payload.get("website_presence")
            checks = (
                presence.get("confirmation_checks")
                if isinstance(presence, dict)
                else None
            )
            verified = (
                isinstance(presence, dict)
                and presence.get("status") == "no_website_found"
                and presence.get("confirmation_attempted") is True
                and isinstance(checks, list)
                and any(
                    isinstance(check, dict)
                    and check.get("status") == "completed"
                    for check in checks
                )
            )
            return (
                verified,
                "No matching website was found by a completed verification search."
                if verified
                else "Missing website status has no completed verification search.",
            )
        if value in {"unavailable", "parked"}:
            enrichment = payload.get("website_enrichment")
            verified = (
                isinstance(enrichment, dict)
                and enrichment.get("availability_status") == value
            )
            return (
                verified,
                "Website availability was verified by direct inspection."
                if verified
                else "Website availability has no matching direct inspection.",
            )
        return False, "Website status does not represent a verified website gap."

    if signal_key in PAGESPEED_GRADE_SIGNALS:
        pagespeed = payload.get("pagespeed_mobile")
        valid = isinstance(pagespeed, dict) and not pagespeed.get("error")
        return (
            valid,
            "Website grade comes from a successful PageSpeed inspection."
            if valid
            else "Website grade does not have a successful PageSpeed inspection.",
        )

    if signal_key not in PAGE_SCOPED_NEGATIVE_SIGNALS:
        return True, "Finding does not require a page-scope assertion."

    enrichment = payload.get("website_enrichment")
    if not isinstance(enrichment, dict):
        return False, "Website finding has no enrichment evidence."
    inspection = enrichment.get("inspection")
    evidence_by_signal = enrichment.get("signal_evidence")
    if not isinstance(inspection, dict) or not isinstance(evidence_by_signal, dict):
        return False, "Website finding has no structured inspection scope."

    evidence = evidence_by_signal.get(signal_key)
    if value is True:
        valid = isinstance(evidence, list) and bool(evidence)
        return (
            valid,
            "The inspected page contains a matching element."
            if valid
            else "Positive website finding has no matching element evidence.",
        )
    if value is not False:
        return False, "Website finding is unknown."

    scope_key = _REQUIRED_SCOPE[signal_key]
    scope = inspection.get("scope")
    complete = isinstance(scope, dict) and scope.get(scope_key) is True
    return (
        complete,
        f"Required inspection scope {scope_key!r} was completed."
        if complete
        else f"Required inspection scope {scope_key!r} was not completed.",
    )
