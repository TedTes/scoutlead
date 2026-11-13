from signal_validation.pitch_scope import pitch_scope_decision


def _website_payload(*, scope: dict, evidence: dict | None = None) -> dict:
    return {
        "website_enrichment": {
            "inspection": {"complete": True, "pages": [], "scope": scope},
            "signal_evidence": evidence or {},
        }
    }


def test_page_absence_requires_the_relevant_page_scope() -> None:
    payload = _website_payload(
        scope={
            "homepage_complete": True,
            "contact_intent_page_complete": False,
            "quote_intent_page_complete": False,
            "mobile_render_complete": False,
        }
    )

    assert pitch_scope_decision("primary_cta_present", False, payload)[0] is True
    assert pitch_scope_decision("click_to_call_present", False, payload)[0] is False


def test_positive_page_finding_requires_element_evidence() -> None:
    without_evidence = _website_payload(scope={"homepage_complete": True})
    with_evidence = _website_payload(
        scope={"homepage_complete": True},
        evidence={
            "primary_cta_present": [
                {"url": "https://example.test", "match": "request an estimate"}
            ]
        },
    )

    assert pitch_scope_decision(
        "primary_cta_present", True, without_evidence
    )[0] is False
    assert pitch_scope_decision("primary_cta_present", True, with_evidence)[0] is True


def test_website_grade_requires_a_successful_pagespeed_result() -> None:
    assert pitch_scope_decision(
        "website_quality_score",
        42,
        {"pagespeed_mobile": {"website_url": "https://example.test"}},
    )[0] is True
    assert pitch_scope_decision(
        "website_quality_score",
        42,
        {"pagespeed_mobile": {"error": "rate limited"}},
    )[0] is False


def test_only_verified_top_level_website_gaps_are_pitch_safe() -> None:
    verified_missing = {
        "website_presence": {
            "status": "no_website_found",
            "confirmation_attempted": True,
            "confirmation_checks": [
                {"provider": "configured_search", "status": "completed"}
            ],
        }
    }
    assert pitch_scope_decision(
        "website_status", "missing", verified_missing
    )[0] is True
    assert pitch_scope_decision("website_status", "missing", {})[0] is False
    assert pitch_scope_decision(
        "website_status",
        "parked",
        {"website_enrichment": {"availability_status": "parked"}},
    )[0] is True
    assert pitch_scope_decision("website_status", "not_listed", {})[0] is False
    assert pitch_scope_decision("website_status", "present", {})[0] is False
