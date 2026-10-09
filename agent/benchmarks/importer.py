from __future__ import annotations

from collections import defaultdict

from benchmarks.schemas import BenchmarkRecord
from db.models import BusinessModel
from quality.fact_policy import FactQualityPolicyService
from quality.repository import QualityRepository, QualityScope


def import_reviewed_records(
    session,
    records: list[BenchmarkRecord],
    *,
    dry_run: bool = True,
) -> dict:
    repository = QualityRepository(session)
    labels_by_dimension: dict[str, list[dict]] = defaultdict(list)
    skipped = 0
    for record in records:
        if not record.labels.reviewer or record.labels.reviewed_at is None:
            skipped += 1
            continue
        if session.get(BusinessModel, record.business_id) is None:
            skipped += 1
            continue
        for dimension, expected, predicted in _record_labels(record):
            labels_by_dimension[dimension].append(
                {
                    "business_id": record.business_id,
                    "expected": expected,
                    "predicted": predicted,
                    "reviewer": record.labels.reviewer,
                    "reviewed_at": record.labels.reviewed_at,
                    "evidence": record.labels.source_urls or record.source_urls,
                    "notes": record.labels.notes,
                    "idempotency_key": (
                        f"benchmark:{record.benchmark_version}:{record.business_id}:"
                        f"{dimension}:{record.labels.reviewed_at.isoformat()}"
                    ),
                }
            )
    summary = {
        "dry_run": dry_run,
        "reviewed_records": len(records) - skipped,
        "skipped_records": skipped,
        "labels": {
            dimension: len(labels)
            for dimension, labels in sorted(labels_by_dimension.items())
        },
    }
    if dry_run:
        return summary
    for dimension, labels in labels_by_dimension.items():
        scope = QualityScope(dimension=dimension)
        for label in labels:
            repository.add_label(
                scope=scope,
                commit=False,
                **label,
            )
        session.commit()
        repository.calculate(scope)
        FactQualityPolicyService(session).reevaluate_dimension(dimension)
    return summary


def _record_labels(record: BenchmarkRecord):
    identity = _truth(record.labels.identity_correct)
    if identity is not None:
        yield "identity", identity, True
        yield "business_identity", identity, True
    trade = _truth(record.labels.trade_correct)
    if trade is not None:
        yield "trade", trade, True
    location = _truth(record.labels.location_correct)
    if location is not None:
        yield "location", location, True

    expected_website = _website_opportunity(record.labels.website_status)
    predicted_website = _website_opportunity(record.observed.website_status)
    if expected_website is not None:
        yield "website_unavailable", expected_website, predicted_website

    if record.labels.review_count is not None:
        yield (
            "reviews_under_15",
            record.labels.review_count < 15,
            (
                record.observed.review_count < 15
                if record.observed.review_count is not None
                else None
            ),
        )

    expected_quote = _negative_truth(record.labels.quote_or_booking_form_present)
    if expected_quote is not None:
        yield (
            "no_quote_flow",
            expected_quote,
            _negative_boolean(record.observed.quote_or_booking_form_present),
        )
    expected_contact = _negative_truth(record.labels.contact_form_present)
    if expected_contact is not None:
        yield (
            "no_contact_form",
            expected_contact,
            _negative_boolean(record.observed.contact_form_present),
        )


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
