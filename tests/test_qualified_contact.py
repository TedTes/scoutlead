from datetime import datetime, timezone

from leads.policy import best_contact_channel, controlled_signal_tags
from leads.schemas import (
    AgentFitStatus,
    BestChannel,
    ContactVerificationStatus,
    LeadRead,
    QualificationResult,
)
from products.schemas import ProductRead, QualificationCriterion
from prompts.approach import approach_prompt


def test_controlled_signal_tags_drop_unknown_values_and_preserve_vocabulary_labels() -> None:
    assert controlled_signal_tags(
        [" fleet vehicles visible ", "invented tag", "OWNER OPERATED"],
        ["Fleet vehicles visible", "Owner operated"],
    ) == ["Fleet vehicles visible", "Owner operated"]
    assert controlled_signal_tags(["anything"], None) == []


def test_best_channel_uses_verified_email_then_phone_form_visit_and_none() -> None:
    lead = _lead(
        contact_email="owner@example.test",
        verification_status=ContactVerificationStatus.VALID,
    )
    assert best_contact_channel(lead)[0] == BestChannel.EMAIL

    phone = _lead(raw_sources=[{"phone": "416-555-0100"}])
    assert best_contact_channel(phone)[0] == BestChannel.PHONE

    form = _lead(raw_sources=[{"website_enrichment": {"has_contact_form": True}}])
    assert best_contact_channel(form)[0] == BestChannel.CONTACT_FORM

    visit = _lead(raw_sources=[{"formatted_address": "100 King St, Toronto"}])
    assert best_contact_channel(visit)[0] == BestChannel.VISIT
    assert best_contact_channel(_lead())[0] == BestChannel.NONE


def test_approach_prompt_enforces_evidence_boundaries() -> None:
    lead = _lead(
        qualification=QualificationResult(
            qualified=True,
            fit_status=AgentFitStatus.GOOD_FIT,
            score=82,
            rationale="Local HVAC contractor.",
            positive_signals=["Service fleet"],
            recommended_next_step="Contact owner.",
        )
    )
    prompt = approach_prompt(_product(), lead, channel=BestChannel.PHONE)

    assert "at most two sentences" in prompt
    assert "exactly three short talk-track bullets" in prompt
    assert "Do not make claims beyond" in prompt
    assert "Do not imply the business has a problem" in prompt


def _lead(**updates) -> LeadRead:
    now = datetime.now(timezone.utc)
    values = {
        "id": "lead:first",
        "campaign_id": "campaign:first",
        "product_id": "product:first",
        "company_name": "Example HVAC",
        "source": "seed",
        "raw_sources": [],
        "status": "qualified",
        "created_at": now,
        "updated_at": now,
    }
    values.update(updates)
    return LeadRead.model_validate(values)


def _product() -> ProductRead:
    now = datetime.now(timezone.utc)
    return ProductRead(
        id="product:first",
        product_name="Contractor Coverage",
        offer_summary="Commercial insurance for contractors.",
        target_customer="HVAC contractors",
        target_geography="Toronto",
        qualification_criteria=[QualificationCriterion(label="HVAC business")],
        created_at=now,
        updated_at=now,
    )
