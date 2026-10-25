from datetime import timedelta
from types import SimpleNamespace

from canonical.normalization import stable_content_hash
from shared.utils import utcnow
from source_observations.integrity import evaluate_observation_integrity


def _observation(**overrides):
    payload = overrides.pop("raw_payload", {"name": "Example Plumbing"})
    values = {
        "id": "observation_1",
        "business_id": "business_1",
        "source": "google_places",
        "external_id": "place_1",
        "source_url": None,
        "query_signature": "query_1",
        "raw_payload": payload,
        "content_hash": stable_content_hash(payload),
        "observed_at": utcnow(),
        **overrides,
    }
    return SimpleNamespace(**values)


def test_intact_observation_passes() -> None:
    result = evaluate_observation_integrity(
        _observation(),
        expected_business_id="business_1",
        expected_sources={"google_places"},
    )

    assert result.status == "passed"
    assert result.confidence == 100


def test_payload_hash_mismatch_fails() -> None:
    result = evaluate_observation_integrity(
        _observation(content_hash="0" * 64),
    )

    assert result.status == "failed"
    assert any(check.name == "content_hash" for check in result.checks if check.status == "failed")


def test_empty_payload_fails() -> None:
    result = evaluate_observation_integrity(_observation(raw_payload={}))

    assert result.status == "failed"
    assert "payload" in " ".join(result.failures).lower()


def test_business_mismatch_fails() -> None:
    result = evaluate_observation_integrity(
        _observation(),
        expected_business_id="business_2",
    )

    assert result.status == "failed"
    assert "different business" in " ".join(result.failures).lower()


def test_stale_observation_requires_review() -> None:
    now = utcnow()
    result = evaluate_observation_integrity(
        _observation(observed_at=now - timedelta(days=91)),
        now=now,
        stale_after=timedelta(days=90),
    )

    assert result.status == "uncertain"
    assert result.confidence == 70


def test_future_observation_requires_review() -> None:
    now = utcnow()
    result = evaluate_observation_integrity(
        _observation(observed_at=now + timedelta(minutes=6)),
        now=now,
    )

    assert result.status == "uncertain"


def test_missing_locator_can_be_enforced_for_audits() -> None:
    result = evaluate_observation_integrity(
        _observation(external_id=None, query_signature=None, source_url=None),
        require_locator=True,
    )

    assert result.status == "uncertain"
