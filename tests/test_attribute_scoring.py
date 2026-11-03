from business_facts.attribute_scoring import score_attribute


def test_boolean_gap_score_is_separate_from_evidence_confidence() -> None:
    scored = score_attribute(
        "contact_form_present",
        False,
        opportunity_direction="false_is_opportunity",
    )

    assert scored.score == 100
    assert scored.reason == "strong opportunity: missing"


def test_unknown_is_not_scored_as_zero() -> None:
    scored = score_attribute("contact_form_present", None)

    assert scored.score is None


def test_positive_boolean_has_no_opportunity_score() -> None:
    scored = score_attribute("contact_form_present", True)

    assert scored.score == 0


def test_listing_gap_does_not_equal_verified_missing_website() -> None:
    listed = score_attribute("website_status", "not_listed")
    missing = score_attribute("website_status", "missing")

    assert listed.score is None
    assert missing.score == 100


def test_numeric_attributes_use_a_gradient() -> None:
    low = score_attribute("google_rating", 2.0)
    high = score_attribute("google_rating", 4.8)

    assert low.score is not None
    assert high.score is not None
    assert low.score > high.score


def test_config_can_define_categorical_scores() -> None:
    scored = score_attribute(
        "custom_attribute",
        "weak",
        config={"score_values": {"weak": 25, "strong": 100}},
    )

    assert scored.score == 25
