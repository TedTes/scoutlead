from datetime import timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from db.models import (
    AudienceResultModel,
    AudienceRunModel,
    BusinessModel,
    LeadModel,
    LeadOutcomeModel,
    MessageModel,
    NicheModel,
    OutreachPackageModel,
    OutreachTemplateModel,
    OutreachEventModel,
    ProductModel,
    TerritoryModel,
)
from db.session import create_database
from outreach_packages.schemas import (
    OutreachEventCreate,
    OutreachGenerateRequest,
    OutreachGenerationInput,
    OutreachMarkSentRequest,
    OutreachPackageUpdate,
    OutreachResponseClassifyRequest,
    OutreachTemplateCreate,
    OutreachTemplateUpdate,
)
from outreach_packages.service import (
    OutreachPackageService,
    OutreachTemplateService,
    _evidence,
)
from leads.workspace import WorkspaceLeadService
from shared.errors import ConfigurationError, ValidationError
from shared.utils import new_id, utcnow


class _StructuredLLM:
    provider = "test-provider"
    model = "test-model"

    def __init__(self, *, invalid_call_first: bool = False) -> None:
        self.last_usage = {"input_tokens": 42, "output_tokens": 17}
        self.calls: list[dict] = []
        self.invalid_call_first = invalid_call_first

    def generate_object(self, **kwargs):
        self.calls.append(kwargs)
        payload = {
                "proposal": {
                    "positive_detail": "A verified 5-star rating across 30 public reviews.",
                    "observed_opportunity": "No quote or booking flow was found in the latest website check.",
                    "proposal_angle": "A simpler quote-request path using the supplied concept.",
                    "proof_url": "https://concept.example/demo",
                },
                "channels": {
                    "instagram": {
                        "initial": "Hi Lakeside Painting — I made a concept for a simpler quote-request path: https://concept.example/demo",
                        "follow_up": "Following up in case the concept link got buried. Happy to walk through it.",
                    },
                    "sms": {
                        "initial": "Hi Lakeside Painting — I made a concept for a simpler quote path. Open to a quick look?",
                        "follow_up": "Following up in case this got buried. Happy to send the link again.",
                    },
                    "email": {
                        "subject": "Website concept for Lakeside Painting",
                        "body": "Hi Lakeside Painting, I made a concept for a simpler quote-request path: https://concept.example/demo",
                        "follow_up_subject": "Following up — Lakeside Painting",
                        "follow_up_body": "Following up in case the website concept got buried. Happy to walk through it.",
                    },
                    "call": {
                        "opener": "Hi, I made a website concept for Lakeside Painting.",
                        "talking_points": ["The current quote path was the opportunity I focused on."],
                        "close": "Would it be useful if I sent the concept link?",
                    },
                },
                "prompt_version": 1,
            }
        if self.invalid_call_first and len(self.calls) == 1:
            payload["channels"]["call"]["opener"] = "x" * 241
        return kwargs["response_model"].model_validate(payload)


def test_boolean_evidence_labels_reflect_the_value() -> None:
    missing = _evidence({"signal_key": "contact_form_present", "value": False})
    present = _evidence({"signal_key": "contact_form_present", "value": True})

    assert missing.label == "Contact form missing"
    assert present.label == "Contact form present"


def test_outreach_package_uses_verified_signal_and_persists_edits() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        service = OutreachPackageService(
            session,
            workspace_id="workspace:first",
        )

        package = service.generate(result.id)

        assert package.channels == ["message", "call", "form", "email"]
        assert package.content.observation == "No quote or booking flow was found in the latest website check."
        assert package.phone == "416-555-0101"
        assert package.contact_url == "https://example.com/contact"
        assert package.provider == "template"
        assert package.model is None
        assert package.usage == {}
        assert "Lakeside Painting" in package.content.message.body
        assert "quote or booking" in package.content.message.body
        assert "quote" in package.content.message.body.lower()
        assert len(package.content.message.body) <= 160
        assert "example" not in package.content.message.body.lower()
        assert len(package.content.evidence_fingerprint) == 64
        assert package.content.reply_paths
        assert package.content.message.body.endswith("?")
        assert package.content.form.body.count("\n\n") >= 5
        assert package.content.call.ask.endswith("?")
        assert package.content.call.discovery_question == (
            "How do customers currently request a quote or schedule work?"
        )
        assert len(package.content.call.branches) == 6
        assert package.content.strategy.service_key == "booking_payments"
        assert package.content.strategy.phrasing_provider == "deterministic"
        assert package.content.message_template is not None
        assert package.content.message_template.lead_reason == package.content.observation
        assert package.content.message_template.opportunity
        assert "Lakeside Painting" in package.content.message_template.opportunity
        assert service.generate(result.id).id == package.id
        assert session.scalar(select(func.count()).select_from(OutreachPackageModel)) == 1

        content = package.content.model_copy(deep=True)
        content.message.body = "Updated message grounded in the same verified opportunity evidence?"
        content.message_template.proof_url = "https://example.com/concept"
        updated = service.update(package.id, OutreachPackageUpdate(content=content))

        assert updated.content.message.body.startswith("Updated message")
        assert updated.content.message_template.proof_url == "https://example.com/concept"
        assert service.find_for_result(result.id).content.message.body == updated.content.message.body

        content = updated.content.model_copy(deep=True)
        content.call.selected_branch = "considered_expensive"
        branched = service.update(package.id, OutreachPackageUpdate(content=content))

        assert branched.content.call.selected_branch == "considered_expensive"

        invalid = branched.content.model_copy(deep=True)
        invalid.call.selected_branch = "invented-response"
        with pytest.raises(ValidationError, match="not part of this outreach playbook"):
            service.update(package.id, OutreachPackageUpdate(content=invalid))

        classification = service.classify_response(
            package.id,
            OutreachResponseClassifyRequest(
                channel="message",
                response_text="We already received an expensive quote for this.",
            ),
        )
        assert classification.category == "considered_expensive"
        assert classification.suggested_reply
        service.record_event(
            package.id,
            OutreachEventCreate(
                channel="message",
                event_type="draft_copied",
                variant_id=package.content.strategy.selected_variant,
            ),
        )
        analytics = service.analytics()
        assert analytics.total_events == 2
        assert analytics.by_event == {"response_classified": 1, "draft_copied": 1}


def test_explicit_generation_uses_provider_neutral_llm_and_persists_handoff() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        llm = _StructuredLLM()
        service = OutreachPackageService(
            session,
            workspace_id="workspace:first",
            llm=llm,
        )

        package = service.generate(
            result.id,
            OutreachGenerateRequest(
                outreach_input=OutreachGenerationInput(
                    channels=["instagram", "email"],
                    review_notes="The contact page is difficult to find from the main navigation.",
                    personal_detail="The business has 30 public reviews.",
                    concept_url="https://concept.example/demo",
                    concept_features=["Guided quote request", "Project gallery"],
                    persuasion_style="direct_specialist",
                )
            ),
        )

        assert len(llm.calls) == 1
        assert llm.calls[0]["task"] == "outreach_channel_generation"
        assert llm.calls[0]["context"]["sender"]["identity"] == "Conversion Studio"
        assert llm.calls[0]["context"]["outreach_input"]["persuasion_style"] == "direct_specialist"
        assert llm.calls[0]["context"]["outreach_input"]["review_notes"] == (
            "The contact page is difficult to find from the main navigation."
        )
        assert "Direct specialist" in llm.calls[0]["system"]
        assert package.provider == "test-provider"
        assert package.model == "test-model"
        assert package.usage == {"input_tokens": 42, "output_tokens": 17}
        assert package.content.outreach_input.concept_features == [
            "Guided quote request",
            "Project gallery",
        ]
        assert package.content.outreach_input.channels == ["instagram", "email"]
        assert package.content.generated_outreach is not None
        assert package.content.generated_outreach.channels.email.subject == (
            "Website concept for Lakeside Painting"
        )
        assert package.content.generated_outreach.proposal.proof_url == (
            "https://concept.example/demo"
        )
        assert service.find_for_result(result.id) is not None
        assert len(llm.calls) == 1

        edited_content = package.content.model_copy(deep=True)
        edited_message = "Hi Lakeside Painting — this is my edited Instagram message."
        edited_content.generated_outreach.channels.instagram.initial = edited_message
        edited = service.update(
            package.id,
            OutreachPackageUpdate(content=edited_content),
        )

        assert edited.content.generated_outreach.channels.instagram.initial == edited_message
        assert (
            service.find_for_result(result.id)
            .content.generated_outreach.channels.instagram.initial
            == edited_message
        )
        assert len(llm.calls) == 1

        expanded = service.generate(
            result.id,
            OutreachGenerateRequest(
                outreach_input=OutreachGenerationInput(channels=["call"])
            ),
        )

        assert len(llm.calls) == 2
        assert expanded.content.generated_outreach.channels.instagram is not None
        assert expanded.content.generated_outreach.channels.email is not None
        assert expanded.content.generated_outreach.channels.call is not None
        assert expanded.content.generated_outreach.channels.sms is None
        assert expanded.content.outreach_input.channels == ["instagram", "email", "call"]


def test_saving_context_does_not_generate_or_replace_existing_drafts() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        llm = _StructuredLLM()
        service = OutreachPackageService(
            session,
            workspace_id="workspace:first",
            llm=llm,
        )

        generated = service.generate(
            result.id,
            OutreachGenerateRequest(
                outreach_input=OutreachGenerationInput(channels=["instagram"])
            ),
        )
        original_message = generated.content.generated_outreach.channels.instagram.initial

        saved = service.save_context(
            result.id,
            OutreachGenerateRequest(
                outreach_input=OutreachGenerationInput(
                    channels=["email"],
                    review_notes="The website navigation hides the quote request page.",
                    personal_detail="Their project gallery shows careful preparation.",
                    concept_url="https://concept.example/new",
                    concept_features=["Project gallery", "Quote request"],
                )
            ),
        )

        assert len(llm.calls) == 1
        assert saved.content.outreach_input.personal_detail == (
            "Their project gallery shows careful preparation."
        )
        assert saved.content.outreach_input.review_notes == (
            "The website navigation hides the quote request page."
        )
        assert saved.content.outreach_input.concept_url == "https://concept.example/new"
        assert saved.content.generated_outreach.channels.instagram.initial == original_message


def test_workspace_shortlist_uses_the_shortlisted_result_id_for_duplicate_business() -> None:
    with _session_factory()() as session:
        unshortlisted = _seed_result(session, confirmed=True)
        unshortlisted.shortlisted_at = None
        first_audience = session.get(TerritoryModel, unshortlisted.audience_id)
        now = utcnow()
        shortlisted_audience = TerritoryModel(
            id=new_id("territory"),
            workspace_id="workspace:first",
            product_id=first_audience.product_id,
            niche_id=first_audience.niche_id,
            market_key="north-york",
            city="North York",
            signal_keys=["no_quote_flow"],
            label="Painters · North York",
            criteria_hash="duplicate-business-test",
        )
        session.add(shortlisted_audience)
        session.flush()
        shortlisted_run = AudienceRunModel(
            id=new_id("audience_run"),
            workspace_id="workspace:first",
            audience_id=shortlisted_audience.id,
            criteria_version=1,
            state="ready",
            requested_count=25,
            result_count=1,
            new_result_count=1,
            deadline_at=now + timedelta(minutes=5),
            completed_at=now,
        )
        session.add(shortlisted_run)
        session.flush()
        shortlisted = AudienceResultModel(
            id=new_id("audience_result"),
            run_id=shortlisted_run.id,
            audience_id=shortlisted_audience.id,
            business_id=unshortlisted.business_id,
            rank_position=1,
            is_new=False,
            shortlisted_at=now,
            match_snapshot=unshortlisted.match_snapshot,
        )
        session.add(shortlisted)
        session.commit()

        page = WorkspaceLeadService(
            session,
            workspace_id="workspace:first",
        ).page(view="shortlisted")

        assert page.total == 1
        assert page.items[0].audience_result_id == shortlisted.id


def test_saved_structure_is_workspace_scoped_and_snapshotted_for_generation() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        templates = OutreachTemplateService(
            session,
            workspace_id="workspace:first",
        )
        saved = templates.create(
            OutreachTemplateCreate(
                name="Proof then question",
                structure="Greeting, verified proof, opportunity, then one question.",
                example="Hi Example Co — your 20 reviews stood out. I made this for you. Open to a look?",
            )
        )
        llm = _StructuredLLM()

        package = OutreachPackageService(
            session,
            workspace_id="workspace:first",
            llm=llm,
        ).generate(
            result.id,
            OutreachGenerateRequest(
                outreach_input=OutreachGenerationInput(
                    channels=["instagram"],
                    structure_template_id=saved.id,
                )
            ),
        )

        assert package.content.outreach_input.structure_template_id == saved.id
        assert package.content.outreach_input.message_structure == saved.structure
        assert package.content.outreach_input.example_message == saved.example
        assert llm.calls[0]["context"]["selected_message_structure"] == saved.structure
        assert llm.calls[0]["context"]["example_message"] == saved.example
        assert "Reproduce only its order, pacing, and rhetorical shape" in llm.calls[0]["system"]
        assert OutreachTemplateService(
            session,
            workspace_id="workspace:other",
        ).list() == []


def test_outreach_template_can_be_updated_cleared_and_deleted() -> None:
    with _session_factory()() as session:
        service = OutreachTemplateService(session, workspace_id="workspace:first")
        saved = service.create(
            OutreachTemplateCreate(
                name="Original",
                structure="Greeting, proof, opportunity, question.",
                example="An example message.",
            )
        )

        updated = service.update(
            saved.id,
            OutreachTemplateUpdate(name="Updated", example=None),
        )

        assert updated.name == "Updated"
        assert updated.example is None
        assert len(service.list()) == 1
        service.delete(saved.id)
        assert service.list() == []
        assert session.get(OutreachTemplateModel, saved.id) is None


def test_mark_sent_moves_shortlisted_result_to_contacted_once() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        service = OutreachPackageService(
            session,
            workspace_id="workspace:first",
            llm=_StructuredLLM(),
        )
        package = service.generate(
            result.id,
            OutreachGenerateRequest(
                outreach_input=OutreachGenerationInput(channels=["instagram"])
            ),
        )

        contacted = service.mark_sent(
            package.id,
            OutreachMarkSentRequest(channel="instagram"),
        )
        repeated = service.mark_sent(
            package.id,
            OutreachMarkSentRequest(channel="instagram"),
        )

        session.refresh(result)
        lead = session.get(LeadModel, result.outreach_lead_id)
        assert result.contacted_at is not None
        assert lead is not None
        assert lead.last_contacted_at is not None
        assert contacted.sent_channels["instagram"] == repeated.sent_channels["instagram"]
        assert session.scalar(select(func.count()).select_from(LeadOutcomeModel)) == 1
        assert session.scalar(select(func.count()).select_from(OutreachEventModel)) == 1
        contacted_page = WorkspaceLeadService(
            session,
            workspace_id="workspace:first",
        ).page(view="contacted")
        assert contacted_page.total == 1
        assert contacted_page.items[0].audience_result_id == result.id


def test_explicit_generation_requires_configured_llm_provider() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        service = OutreachPackageService(
            session,
            workspace_id="workspace:first",
        )

        with pytest.raises(ConfigurationError, match="real LLM provider is required"):
            service.generate(
                result.id,
                OutreachGenerateRequest(
                    outreach_input=OutreachGenerationInput(channels=["instagram"])
                ),
            )


def test_outreach_generation_retries_invalid_structured_response_once() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        llm = _StructuredLLM(invalid_call_first=True)
        service = OutreachPackageService(
            session,
            workspace_id="workspace:first",
            llm=llm,
        )

        package = service.generate(
            result.id,
            OutreachGenerateRequest(
                outreach_input=OutreachGenerationInput(channels=["call"])
            ),
        )

        assert len(llm.calls) == 2
        assert "previous structured response failed validation" in llm.calls[1]["system"]
        assert package.content.generated_outreach.channels.call is not None
        assert len(package.content.generated_outreach.channels.call.opener) <= 240


def test_outreach_package_handoff_snapshots_one_message() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        service = OutreachPackageService(session, workspace_id="workspace:first")
        package = service.generate(result.id)

        message = service.prepare_message(package.id)
        repeated = service.prepare_message(package.id)

        assert repeated.id == message.id
        assert message.outreach_package_id == package.id
        assert message.subject == package.content.email.subject
        assert message.body == package.content.email.body
        assert message.status.value == "pending_approval"
        assert session.scalar(select(func.count()).select_from(MessageModel)) == 1


def test_outreach_package_refreshes_when_evidence_snapshot_changes() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        service = OutreachPackageService(session, workspace_id="workspace:first")
        package = service.generate(result.id)
        original_fingerprint = package.content.evidence_fingerprint
        snapshot = dict(result.match_snapshot)
        raw = dict(snapshot["raw"])
        profile_match = dict(raw["profile_match"])
        matched = [dict(item) for item in profile_match["matched_signals"]]
        matched[0]["source_evidence_id"] = "business_evidence:new"
        profile_match["matched_signals"] = matched
        raw["profile_match"] = profile_match
        snapshot["raw"] = raw
        result.match_snapshot = snapshot
        session.commit()

        refreshed = service.find_for_result(result.id)

        assert refreshed is not None
        assert refreshed.content.evidence_fingerprint != original_fingerprint


def test_outreach_package_refreshes_older_template_copy() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        service = OutreachPackageService(session, workspace_id="workspace:first")
        package = service.generate(result.id)
        row = session.get(OutreachPackageModel, package.id)
        stale_content = dict(row.content)
        stale_content["message"] = {
            "body": (
                "Hi Lakeside Painting, I help residential painting contractors in "
                "scarborough on businesses in Toronto with websites."
            )
        }
        row.content = stale_content
        row.prompt_version = 1
        session.commit()

        refreshed = service.find_for_result(result.id)

        assert refreshed is not None
        assert "on businesses in" not in refreshed.content.message.body
        assert "quote" in refreshed.content.message.body.lower()
        assert len(refreshed.content.message.body) <= 160
        assert row.prompt_version == 12


def test_outreach_package_preserves_edited_older_template_copy() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        service = OutreachPackageService(session, workspace_id="workspace:first")
        package = service.generate(result.id)
        row = session.get(OutreachPackageModel, package.id)
        custom_body = "Hi Lakeside Painting, I wrote this custom message and want to keep it."
        custom_content = dict(row.content)
        custom_content["message"] = {"body": custom_body}
        custom_content.pop("strategy", None)
        row.content = custom_content
        row.prompt_version = 1
        session.commit()

        preserved = service.find_for_result(result.id)

        assert preserved is not None
        assert preserved.content.message.body == custom_body
        assert preserved.content.strategy is not None
        assert preserved.content.call.branches
        assert session.get(OutreachPackageModel, package.id).prompt_version == 12


def test_outreach_package_uses_safe_fallback_for_shortlisted_business_without_verified_opportunity() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=False)
        service = OutreachPackageService(
            session,
            workspace_id="workspace:first",
        )

        package = service.generate(result.id)

        assert package.content.strategy.primary_signal_key == "shortlisted_interest"
        assert "website is outdated" not in package.content.message.body.lower()
        assert "losing customers" not in package.content.message.body.lower()


def test_outreach_package_uses_safe_fallback_when_claim_lacks_pitch_scope() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        snapshot = dict(result.match_snapshot)
        raw = dict(snapshot["raw"])
        profile_match = dict(raw["profile_match"])
        matched = [dict(item) for item in profile_match["matched_signals"]]
        matched[0]["pitch_eligible"] = False
        profile_match["matched_signals"] = matched
        raw["profile_match"] = profile_match
        snapshot["raw"] = raw
        result.match_snapshot = snapshot
        session.commit()

        package = OutreachPackageService(
            session,
            workspace_id="workspace:first",
        ).generate(result.id)

        assert package.content.strategy.primary_signal_key == "shortlisted_interest"


def test_outreach_package_uses_safe_fallback_for_unsupported_service_signal_pair() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        audience = session.get(TerritoryModel, result.audience_id)
        audience.service_keys = ["website_modernization"]
        snapshot = dict(result.match_snapshot)
        raw = dict(snapshot["raw"])
        raw["profile_match"] = {
            "confirmed_signal_count": 1,
            "matched_signals": [
                {
                    "signal_key": "google_review_count",
                    "value": 5,
                    "confidence": "confirmed",
                    "pitch_eligible": True,
                }
            ],
        }
        snapshot["raw"] = raw
        result.match_snapshot = snapshot
        session.commit()

        package = OutreachPackageService(
            session,
            workspace_id="workspace:first",
        ).generate(result.id)

        assert package.content.strategy.primary_signal_key == "shortlisted_interest"


def test_outreach_package_ignores_possible_evidence_when_confirmed_exists() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        snapshot = dict(result.match_snapshot)
        raw = dict(snapshot["raw"])
        profile_match = dict(raw["profile_match"])
        profile_match["matched_signals"] = [
            {
                "signal_key": "website_status",
                "fact_key": "website_status",
                "value": "not_listed",
                "confidence": "possible",
            },
            {
                "signal_key": "no_quote_flow",
                "fact_key": "quote_or_booking_form_present",
                "value": False,
                "confidence": "confirmed",
                "pitch_eligible": True,
            },
        ]
        raw["profile_match"] = profile_match
        snapshot["raw"] = raw
        result.match_snapshot = snapshot
        session.commit()
        service = OutreachPackageService(
            session,
            workspace_id="workspace:first",
        )

        package = service.generate(result.id)

        assert package.content.observation.startswith("No quote")


def test_outreach_package_uses_safe_fallback_for_unconfirmed_website_observation() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=False)
        snapshot = dict(result.match_snapshot)
        raw = dict(snapshot["raw"])
        raw["profile_match"] = {
            "confirmed_signal_count": 0,
            "matched_signals": [
                {
                    "signal_key": "website_status",
                    "fact_key": "website_status",
                    "value": "not_listed",
                    "confidence": "possible",
                }
            ],
        }
        snapshot["raw"] = raw
        result.match_snapshot = snapshot
        session.commit()
        service = OutreachPackageService(
            session,
            workspace_id="workspace:first",
        )

        package = service.generate(result.id)

        assert package.content.strategy.primary_signal_key == "shortlisted_interest"


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed_result(session, *, confirmed: bool) -> AudienceResultModel:
    now = utcnow()
    product = ProductModel(
        id=new_id("product"),
        workspace_id="workspace:first",
        product_name="Conversion Studio",
        target_customer="Local service businesses",
        target_geography="Toronto",
        qualification_criteria=[],
        preferred_discovery_sources=[],
        constraints=[],
        ideal_customer_signals=[],
        exclusions=[],
        offer_summary="Online booking and conversion improvements for local contractors.",
        outreach_objective="Ask whether a short example would be useful.",
    )
    niche = NicheModel(
        id=new_id("niche"),
        slug="painters",
        label="Painters",
        category="Home services",
        active=True,
        signal_vocabulary=[],
    )
    business = BusinessModel(
        id=new_id("business"),
        display_name="Lakeside Painting",
        normalized_name="lakeside painting",
        website_url="https://example.com",
        domain="example.com",
        phone="416-555-0101",
        geography="Toronto",
        category_key="painters",
        market_key="toronto",
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add_all([product, niche, business])
    session.flush()
    audience = TerritoryModel(
        id=new_id("territory"),
        workspace_id="workspace:first",
        product_id=product.id,
        niche_id=niche.id,
        market_key="toronto",
        city="Toronto",
        signal_keys=["no_quote_flow"] if confirmed else [],
        label="Painters · Toronto",
        criteria_hash="test",
    )
    session.add(audience)
    session.flush()
    run = AudienceRunModel(
        id=new_id("audience_run"),
        workspace_id="workspace:first",
        audience_id=audience.id,
        criteria_version=1,
        state="ready",
        requested_count=25,
        result_count=1,
        new_result_count=1,
        deadline_at=now + timedelta(minutes=5),
        completed_at=now,
    )
    session.add(run)
    session.flush()
    matched = [
        {
            "signal_key": "no_quote_flow",
            "fact_key": "quote_or_booking_form_present",
            "value": False,
            "confidence": "confirmed",
            "pitch_eligible": True,
        }
    ] if confirmed else []
    result = AudienceResultModel(
        id=new_id("audience_result"),
        run_id=run.id,
        audience_id=audience.id,
        business_id=business.id,
        rank_position=1,
        is_new=True,
        shortlisted_at=now,
        match_snapshot={
            "title": business.display_name,
            "url": business.website_url,
            "contact_email": "owner@example.com",
            "raw": {
                "contact_url": "https://example.com/contact",
                "profile_match": {
                    "confirmed_signal_count": 1 if confirmed else 0,
                    "matched_signals": matched,
                },
            },
        },
    )
    session.add(result)
    session.commit()
    return result
