from datetime import datetime, timezone

from benchmarks.evaluator import evaluate_records
from benchmarks.schemas import (
    BenchmarkLabels,
    BenchmarkObserved,
    BenchmarkRecord,
)


def _record(*, website_observed, website_expected, reviews_observed, reviews_expected):
    return BenchmarkRecord(
        business_id=f"business-{reviews_observed}",
        display_name="Example Business",
        observed=BenchmarkObserved(
            website_status=website_observed,
            review_count=reviews_observed,
        ),
        labels=BenchmarkLabels(
            identity_correct="yes",
            trade_correct="yes",
            location_correct="yes",
            website_status=website_expected,
            review_count=reviews_expected,
            reviewer="reviewer@example.com",
            reviewed_at=datetime.now(timezone.utc),
        ),
    )


def test_benchmark_reports_false_positive_and_fails_gate() -> None:
    report = evaluate_records(
        [
            _record(
                website_observed="missing",
                website_expected="present",
                reviews_observed=8,
                reviews_expected=8,
            ),
            _record(
                website_observed="present",
                website_expected="present",
                reviews_observed=20,
                reviews_expected=20,
            ),
        ]
    )

    assert report.metrics["website_unavailable"].false_positive == 1
    assert report.metrics["reviews_under_15"].precision == 1.0
    assert report.gate.passed is False


def test_unknown_predictions_are_not_treated_as_negative_evidence() -> None:
    report = evaluate_records(
        [
            _record(
                website_observed="not_listed",
                website_expected="missing",
                reviews_observed=None,
                reviews_expected=8,
            )
        ],
        thresholds={"website_unavailable": 0.95},
    )

    assert report.metrics["website_unavailable"].unknown_prediction == 1
    assert report.metrics["website_unavailable"].false_negative == 0
    assert report.gate.passed is False


def test_benchmark_gate_requires_review_volume_and_requested_scope() -> None:
    record = _record(
        website_observed="missing",
        website_expected="missing",
        reviews_observed=8,
        reviews_expected=8,
    ).model_copy(
        update={
            "sampled_niche": "home_service_hvac",
            "market_key": "toronto",
        }
    )

    report = evaluate_records(
        [record],
        thresholds={"identity": 0.9},
        minimum_reviewed=1,
        minimum_labels_per_metric=1,
        required_niches={"home_service_roofing"},
        required_markets={"toronto"},
        minimum_scope_reviewed=1,
    )

    assert report.coverage.reviewed_by_niche == {"home_service_hvac": 1}
    assert report.coverage.reviewed_by_market == {"toronto": 1}
    assert report.gate.passed is False
    assert any("home_service_roofing" in failure for failure in report.gate.failures)
