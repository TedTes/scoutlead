from datetime import timedelta
from types import SimpleNamespace

from canonical.normalization import stable_content_hash
from scripts.audit_source_observations import audit_downstream_links, audit_observations
from shared.utils import utcnow


def _observation(
    observation_id: str,
    business_id: str,
    *,
    payload: dict,
    content_hash: str | None = None,
):
    return SimpleNamespace(
        id=observation_id,
        business_id=business_id,
        source="google_places",
        external_id="shared_place_id",
        query_signature="query_signature",
        source_url=None,
        raw_payload=payload,
        content_hash=content_hash or stable_content_hash(payload),
        observed_at=utcnow() - timedelta(days=1),
    )


def test_audit_summarizes_integrity_duplicates_and_identity_collisions() -> None:
    payload = {"name": "Example Services"}
    observations = [
        _observation("observation_1", "business_1", payload=payload),
        _observation("observation_2", "business_1", payload=payload),
        _observation(
            "observation_3",
            "business_2",
            payload={"name": "Other Services"},
            content_hash="0" * 64,
        ),
    ]

    report = audit_observations(
        observations,
        include_details=True,
        detail_limit=10,
    )

    assert report["summary"]["observations_scanned"] == 3
    assert report["summary"]["status_counts"] == {"failed": 1, "passed": 2}
    assert report["summary"]["issue_counts_by_source"] == {
        "google_places": {"failed:content_hash": 1}
    }
    assert report["summary"]["duplicate_content_groups"] == 1
    assert report["summary"]["cross_business_external_id_collisions"] == 1
    assert report["affected_observations"][0]["observation_id"] == "observation_3"


def test_downstream_audit_finds_published_fact_on_invalid_observation() -> None:
    observation = _observation(
        "observation_1",
        "business_1",
        payload={"name": "Example Services"},
        content_hash="0" * 64,
    )
    claim = SimpleNamespace(
        id="claim_1",
        business_id="business_1",
        source_observation_id="observation_1",
    )
    fact = SimpleNamespace(
        id="fact_1",
        business_id="business_1",
        source_observation_id="observation_1",
        supporting_claim_ids=["claim_1"],
        quality_state="published",
    )

    report = audit_downstream_links([observation], [claim], [fact])

    assert report["critical_issue_count"] == 1
    assert report["issue_counts"] == {
        "published_fact_with_invalid_observation": 1
    }
