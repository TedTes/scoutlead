from datetime import timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from db.models import (
    AudienceResultModel,
    AudienceRunModel,
    BusinessModel,
    NicheModel,
    OutreachPackageModel,
    ProductModel,
    TerritoryModel,
)
from db.session import create_database
from outreach_packages.schemas import (
    OutreachEventCreate,
    OutreachPackageUpdate,
    OutreachResponseClassifyRequest,
)
from outreach_packages.service import OutreachPackageService
from shared.errors import ValidationError, WorkflowBoundaryError
from shared.utils import new_id, utcnow


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
        assert package.content.strategy.customer_consequence in package.content.message.body
        assert len(package.content.alternatives) == 6
        assert package.content.reply_paths
        assert package.content.message.body.count("\n\n") >= 3
        assert package.content.form.body.count("\n\n") >= 5
        assert package.content.call.ask.endswith("?")
        assert package.content.call.discovery_question == (
            "How do customers currently request a quote or schedule work?"
        )
        assert len(package.content.call.branches) == 6
        assert package.content.strategy.service_key == "booking_payments"
        assert package.content.strategy.phrasing_provider == "deterministic"
        assert service.generate(result.id).id == package.id
        assert session.scalar(select(func.count()).select_from(OutreachPackageModel)) == 1

        content = package.content.model_copy(deep=True)
        content.message.body = "Updated message grounded in the same verified opportunity evidence."
        updated = service.update(package.id, OutreachPackageUpdate(content=content))

        assert updated.content.message.body.startswith("Updated message")
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
        assert refreshed.content.strategy.customer_consequence in refreshed.content.message.body
        assert row.prompt_version == 6


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
        assert session.get(OutreachPackageModel, package.id).prompt_version == 6


def test_outreach_package_rejects_unverified_opportunity() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=False)
        service = OutreachPackageService(
            session,
            workspace_id="workspace:first",
        )

        with pytest.raises(WorkflowBoundaryError, match="verified opportunity"):
            service.generate(result.id)


def test_outreach_package_rejects_unsupported_service_signal_pair() -> None:
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
                }
            ],
        }
        snapshot["raw"] = raw
        result.match_snapshot = snapshot
        session.commit()

        with pytest.raises(WorkflowBoundaryError, match="No supported outreach playbook"):
            OutreachPackageService(
                session,
                workspace_id="workspace:first",
            ).generate(result.id)


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


def test_outreach_package_uses_grounded_not_listed_website_observation() -> None:
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

        assert package.content.observation == (
            "The latest business listing does not include a website."
        )
        assert "business listing" in package.content.message.body
        assert "If you already have a website" in package.content.message.body
        assert "homeowners" in package.content.message.body.lower()
        assert "you do not have a website" not in package.content.message.body.lower()
        assert package.content.message.body.endswith("?")


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
        trade_keys=["painters"],
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
    matched = [{"signal_key": "no_quote_flow", "fact_key": "quote_or_booking_form_present", "value": False}] if confirmed else []
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
