from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from benchmarks.schemas import (
    BenchmarkGate,
    BenchmarkCoverage,
    BenchmarkRecord,
    BenchmarkReport,
    MetricResult,
)


DEFAULT_THRESHOLDS = {
    "identity": 0.98,
    "trade": 0.98,
    "location": 0.98,
    "reviews_under_15": 0.98,
    "website_unavailable": 0.95,
    "no_quote_flow": 0.90,
    "no_contact_form": 0.90,
}


@dataclass(frozen=True)
class _BinaryCase:
    expected: bool | None
    predicted: bool | None


def evaluate_records(
    records: Iterable[BenchmarkRecord],
    *,
    thresholds: dict[str, float] | None = None,
    minimum_reviewed: int = 200,
    minimum_labels_per_metric: int = 50,
    required_niches: set[str] | None = None,
    required_markets: set[str] | None = None,
    minimum_scope_reviewed: int = 30,
) -> BenchmarkReport:
    rows = list(records)
    metrics = {
        "identity": _agreement(rows, lambda row: _truth(row.labels.identity_correct)),
        "trade": _agreement(rows, lambda row: _truth(row.labels.trade_correct)),
        "location": _agreement(rows, lambda row: _truth(row.labels.location_correct)),
        "reviews_under_15": _binary_metric(
            _signal_cases(
                rows,
                expected=lambda row: (
                    row.labels.review_count < 15
                    if row.labels.review_count is not None
                    else None
                ),
                predicted=lambda row: (
                    row.observed.review_count < 15
                    if row.observed.review_count is not None
                    else None
                ),
            )
        ),
        "website_unavailable": _binary_metric(
            _signal_cases(
                rows,
                expected=lambda row: _website_opportunity(row.labels.website_status),
                predicted=lambda row: _website_opportunity(row.observed.website_status),
            )
        ),
        "no_quote_flow": _binary_metric(
            _signal_cases(
                rows,
                expected=lambda row: _negative_truth(
                    row.labels.quote_or_booking_form_present
                ),
                predicted=lambda row: _negative_boolean(
                    row.observed.quote_or_booking_form_present
                ),
            )
        ),
        "no_contact_form": _binary_metric(
            _signal_cases(
                rows,
                expected=lambda row: _negative_truth(row.labels.contact_form_present),
                predicted=lambda row: _negative_boolean(row.observed.contact_form_present),
            )
        ),
    }
    reviewed = [row for row in rows if row.labels.reviewer and row.labels.reviewed_at]
    coverage = BenchmarkCoverage(
        reviewed_by_niche=dict(
            Counter(row.sampled_niche for row in reviewed if row.sampled_niche)
        ),
        reviewed_by_market=dict(
            Counter(row.market_key for row in reviewed if row.market_key)
        ),
    )
    gate = _gate(
        metrics,
        thresholds or DEFAULT_THRESHOLDS,
        reviewed_count=len(reviewed),
        minimum_reviewed=minimum_reviewed,
        minimum_labels_per_metric=minimum_labels_per_metric,
        coverage=coverage,
        required_niches=required_niches or set(),
        required_markets=required_markets or set(),
        minimum_scope_reviewed=minimum_scope_reviewed,
    )
    versions = {row.benchmark_version for row in rows}
    return BenchmarkReport(
        benchmark_version=next(iter(versions)) if len(versions) == 1 else "mixed",
        record_count=len(rows),
        reviewed_count=len(reviewed),
        coverage=coverage,
        metrics=metrics,
        gate=gate,
    )


def _agreement(
    rows: list[BenchmarkRecord],
    expected: Callable[[BenchmarkRecord], bool | None],
) -> MetricResult:
    values = [expected(row) for row in rows]
    labeled = [value for value in values if value is not None]
    correct = sum(value is True for value in labeled)
    return MetricResult(
        labeled=len(labeled),
        correct=correct,
        accuracy=_ratio(correct, len(labeled)),
        precision=_ratio(correct, len(labeled)),
        recall=_ratio(correct, len(labeled)),
    )


def _signal_cases(
    rows: list[BenchmarkRecord],
    *,
    expected: Callable[[BenchmarkRecord], bool | None],
    predicted: Callable[[BenchmarkRecord], bool | None],
) -> list[_BinaryCase]:
    return [_BinaryCase(expected(row), predicted(row)) for row in rows]


def _binary_metric(cases: list[_BinaryCase]) -> MetricResult:
    labeled = [case for case in cases if case.expected is not None]
    true_positive = sum(case.expected is True and case.predicted is True for case in labeled)
    false_positive = sum(case.expected is False and case.predicted is True for case in labeled)
    false_negative = sum(case.expected is True and case.predicted is False for case in labeled)
    unknown_prediction = sum(case.predicted is None for case in labeled)
    correct = sum(case.expected == case.predicted for case in labeled)
    return MetricResult(
        labeled=len(labeled),
        correct=correct,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        unknown_prediction=unknown_prediction,
        accuracy=_ratio(correct, len(labeled)),
        precision=_ratio(true_positive, true_positive + false_positive),
        recall=_ratio(true_positive, true_positive + false_negative),
    )


def _gate(
    metrics: dict[str, MetricResult],
    thresholds: dict[str, float],
    *,
    reviewed_count: int,
    minimum_reviewed: int,
    minimum_labels_per_metric: int,
    coverage: BenchmarkCoverage,
    required_niches: set[str],
    required_markets: set[str],
    minimum_scope_reviewed: int,
) -> BenchmarkGate:
    failures: list[str] = []
    if reviewed_count < minimum_reviewed:
        failures.append(
            f"reviewed records: {reviewed_count} is below {minimum_reviewed}"
        )
    for key, threshold in thresholds.items():
        metric = metrics.get(key)
        if metric is None or metric.labeled < minimum_labels_per_metric:
            labeled = metric.labeled if metric else 0
            failures.append(
                f"{key}: {labeled} reviewed labels is below {minimum_labels_per_metric}"
            )
            continue
        score = metric.precision
        if score is None or score < threshold:
            rendered = "n/a" if score is None else f"{score:.3f}"
            failures.append(f"{key}: precision {rendered} is below {threshold:.3f}")
    for niche in sorted(required_niches):
        count = coverage.reviewed_by_niche.get(niche, 0)
        if count < minimum_scope_reviewed:
            failures.append(
                f"niche {niche}: {count} reviewed records is below {minimum_scope_reviewed}"
            )
    for market in sorted(required_markets):
        count = coverage.reviewed_by_market.get(market, 0)
        if count < minimum_scope_reviewed:
            failures.append(
                f"market {market}: {count} reviewed records is below {minimum_scope_reviewed}"
            )
    return BenchmarkGate(passed=not failures, failures=failures)


def _truth(value: str) -> bool | None:
    if value == "yes":
        return True
    if value == "no":
        return False
    return None


def _negative_truth(value: str) -> bool | None:
    truth = _truth(value)
    return None if truth is None else not truth


def _negative_boolean(value: bool | None) -> bool | None:
    return None if value is None else not value


def _website_opportunity(value: str | None) -> bool | None:
    if value in {"missing", "unavailable", "parked"}:
        return True
    if value == "present":
        return False
    return None


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None
