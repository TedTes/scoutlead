from scoring import CandidateComponent, candidate_score


def test_candidate_score_uses_attribute_value_confidence_and_freshness() -> None:
    result = candidate_score(
        [
            CandidateComponent(
                key="identity",
                label="Identity",
                group="eligibility",
                weight=20,
                match_value=1,
                confidence=90,
                freshness=1,
                hard_gate=True,
                status="passed",
            ),
            CandidateComponent(
                key="contact_form_present",
                label="Missing contact form",
                group="opportunity",
                weight=80,
                match_value=0.75,
                confidence=80,
                freshness=0.5,
                status="matched",
            ),
        ],
        opportunity_scoped=True,
        opportunity_matched=True,
    )

    assert result["score"] == 42.0
    assert result["state"] == "eligible"
    assert result["components"][0]["contribution"] == 18.0
    assert result["components"][1]["contribution"] == 24.0


def test_hard_gate_failure_disqualifies_a_high_opportunity_score() -> None:
    result = candidate_score(
        [
            CandidateComponent(
                key="trade",
                label="Trade",
                group="eligibility",
                weight=20,
                match_value=0,
                confidence=100,
                hard_gate=True,
                status="failed",
                reason="Wrong trade",
            ),
            CandidateComponent(
                key="website_status",
                label="No website",
                group="opportunity",
                weight=80,
                match_value=1,
                confidence=100,
                status="matched",
            ),
        ],
        opportunity_scoped=True,
        opportunity_matched=True,
    )

    assert result["score"] == 80.0
    assert result["state"] == "disqualified"
    assert result["disqualifiers"] == ["Wrong trade"]


def test_score_is_not_presented_without_an_opportunity_context() -> None:
    result = candidate_score(
        [
            CandidateComponent(
                key="identity",
                label="Identity",
                group="eligibility",
                weight=15,
                match_value=1,
                confidence=100,
                hard_gate=True,
                status="passed",
            )
        ],
        opportunity_scoped=False,
        opportunity_matched=None,
    )

    assert result["score"] is None
    assert result["state"] == "not_scoped"
