from signal_collection.service import _normalized_pagespeed_payload
from territories.matching import _evidence_result_sort_key


def _pagespeed_payload(categories: dict[str, float]) -> dict:
    return {
        "lighthouseResult": {
            "categories": {
                key: {"score": value / 100} for key, value in categories.items()
            },
            "audits": {},
        }
    }


def test_website_quality_grade_requires_all_lighthouse_categories() -> None:
    partial = _normalized_pagespeed_payload(
        _pagespeed_payload(
            {
                "performance": 40,
                "accessibility": 80,
                "best-practices": 70,
            }
        )
    )
    complete = _normalized_pagespeed_payload(
        _pagespeed_payload(
            {
                "performance": 40,
                "accessibility": 80,
                "best-practices": 70,
                "seo": 90,
            }
        )
    )

    assert partial is not None
    assert partial["website_quality_score"] is None
    assert complete is not None
    assert complete["website_quality_score"] == 70


def test_verified_missing_website_ranks_before_upgrade_even_when_farther_away() -> None:
    missing = {
        "raw": {
            "profile_match": {
                "matched_signals": [{"fact_key": "website_status", "value": "missing"}],
                "website_improvement_score": 100,
                "opportunity_score": 80,
                "service_score": 1,
                "confirmed_signal_count": 1,
                "matched_signal_count": 1,
                "distance_km": 20,
            }
        }
    }
    upgrade = {
        "raw": {
            "profile_match": {
                "matched_signals": [
                    {"fact_key": "contact_form_present", "value": False}
                ],
                "website_improvement_score": 95,
                "opportunity_score": 95,
                "service_score": 1,
                "confirmed_signal_count": 1,
                "matched_signal_count": 1,
                "distance_km": 1,
            }
        }
    }
    missing_row = {"id": "missing", "membership_confidence": 1}
    upgrade_row = {"id": "upgrade", "membership_confidence": 1}

    ordered = sorted(
        [(upgrade, upgrade_row), (missing, missing_row)],
        key=_evidence_result_sort_key,
    )

    assert ordered[0][0] is missing
