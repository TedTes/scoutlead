from datetime import timedelta

from business_attributes.eligibility import fact_is_eligible
from db.models import BusinessAttributeModel
from shared.utils import utcnow

def _fact(*, value="missing", confidence=100, resolution="confirmed", expires_at=None, with_source=True):
    return BusinessAttributeModel(
        id="fact:test",
        business_id="business:test",
        row_type="attribute",
        attribute_key="website_status",
        value_type="text",
        value_text=value,
        value_number=None,
        value_boolean=None,
        confidence=confidence,
        resolution_state=resolution,
        supporting_evidence_ids=["observation:test"] if with_source else [],
        observed_at=utcnow(),
        expires_at=expires_at,
        source_content_hash="a" * 64 if with_source else None,
        evidence={},
        resolver_version=1,
    )


def test_fact_eligibility_accepts_current_confirmed_published_evidence() -> None:
    fact = _fact(expires_at=utcnow() + timedelta(days=1))

    assert fact_is_eligible(fact, minimum_confidence=90)


def test_fact_eligibility_rejects_untrusted_states() -> None:
    assert not fact_is_eligible(_fact(), minimum_confidence=90)
    assert not fact_is_eligible(_fact(value="unknown"), minimum_confidence=90)
    assert not fact_is_eligible(_fact(confidence=0), minimum_confidence=90)
    assert not fact_is_eligible(_fact(resolution="conflicted"), minimum_confidence=90)
    assert not fact_is_eligible(
        _fact(expires_at=utcnow() - timedelta(seconds=1)),
        minimum_confidence=90,
    )
    assert not fact_is_eligible(_fact(with_source=False), minimum_confidence=90)
