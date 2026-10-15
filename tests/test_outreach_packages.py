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
    CallDraft,
    EmailDraft,
    OutreachGeneration,
    OutreachPackageUpdate,
    WrittenDraft,
)
from outreach_packages.service import OutreachPackageService
from shared.errors import WorkflowBoundaryError
from shared.utils import new_id, utcnow


class DraftLLM:
    last_usage = {"input_tokens": 20, "output_tokens": 40}

    def __init__(self, expected_observation: str = "No quote") -> None:
        self.expected_observation = expected_observation

    def generate_object(self, **kwargs):
        assert kwargs["task"] == "outreach_package_v1"
        assert kwargs["context"]["verified_observation"].startswith(
            self.expected_observation
        )
        return OutreachGeneration(
            message=WrittenDraft(body="I noticed your site does not currently show an online quote flow. Open to a quick example?"),
            call=CallDraft(
                opener="Hi, is this the owner or manager?",
                observation="I noticed the website does not currently show an online quote flow.",
                ask="Would a quick example be useful?",
            ),
            form=WrittenDraft(body="I noticed the website does not currently show an online quote flow. Would a quick example be useful?"),
            email=EmailDraft(
                subject="Quick question about online quotes",
                body="I noticed the website does not currently show an online quote flow. Would a quick example be useful?",
            ),
        )


def test_outreach_package_uses_verified_signal_and_persists_edits() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=True)
        service = OutreachPackageService(
            session,
            llm=DraftLLM(),
            workspace_id="workspace:first",
            provider="anthropic",
            model="claude-test",
        )

        package = service.generate(result.id)

        assert package.channels == ["message", "call", "form", "email"]
        assert package.content.observation == "No quote or booking flow was found in the latest website check."
        assert package.phone == "416-555-0101"
        assert package.contact_url == "https://example.com/contact"
        assert service.generate(result.id).id == package.id
        assert session.scalar(select(func.count()).select_from(OutreachPackageModel)) == 1

        content = package.content.model_copy(deep=True)
        content.message.body = "Updated message grounded in the same verified opportunity evidence."
        updated = service.update(package.id, OutreachPackageUpdate(content=content))

        assert updated.content.message.body.startswith("Updated message")
        assert service.find_for_result(result.id).content.message.body == updated.content.message.body


def test_outreach_package_rejects_unverified_opportunity() -> None:
    with _session_factory()() as session:
        result = _seed_result(session, confirmed=False)
        service = OutreachPackageService(
            session,
            llm=DraftLLM(),
            workspace_id="workspace:first",
            provider="anthropic",
            model="claude-test",
        )

        with pytest.raises(WorkflowBoundaryError, match="verified opportunity"):
            service.generate(result.id)


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
            llm=DraftLLM(),
            workspace_id="workspace:first",
            provider="anthropic",
            model="claude-test",
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
            llm=DraftLLM("The latest business listing"),
            workspace_id="workspace:first",
            provider="anthropic",
            model="claude-test",
        )

        package = service.generate(result.id)

        assert package.content.observation == (
            "The latest business listing does not include a website."
        )


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
