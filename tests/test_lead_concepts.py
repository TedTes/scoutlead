from datetime import timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from db.models import (
    AudienceResultModel,
    AudienceRunModel,
    BusinessModel,
    LeadConceptModel,
    NicheModel,
    ProductModel,
    TerritoryModel,
)
from db.session import create_database
from outreach_packages.concepts import LeadConceptService
from outreach_packages.schemas import LeadConceptUpsert
from shared.utils import new_id, utcnow


def test_concept_handoff_persists_external_copy_and_tracks_send() -> None:
    with _session_factory()() as session:
        result = _seed_result(session)
        service = LeadConceptService(session, workspace_id="workspace:first")

        assert service.find_for_result(result.id) is None
        draft = service.upsert(
            result.id,
            LeadConceptUpsert(
                concept_type="website_redesign",
                concept_url="https://lakeside-concept.example",
                personalization_note="The preparation photos show careful work.",
                feature_highlights=[
                    "Before and after gallery",
                    "Mobile quote request",
                ],
                instagram_message="Hey! I made a concept for Lakeside Painting: https://lakeside-concept.example",
                follow_up_message="Just floating this back up in case it got buried.",
                call_opener="Hi, I made a website concept for Lakeside Painting.",
            ),
        )

        assert draft.status == "draft"
        assert "https://lakeside-concept.example" in draft.instagram_message
        assert draft.call_opener == "Hi, I made a website concept for Lakeside Painting."
        assert "outdated" not in draft.instagram_message.lower()

        ready = service.upsert(
            result.id,
            LeadConceptUpsert(
                concept_type="website_redesign",
                concept_url="https://lakeside-concept.example",
                personalization_note=draft.personalization_note,
                feature_highlights=draft.feature_highlights,
                concept_banner_confirmed=True,
                noindex_confirmed=True,
                instagram_message=draft.instagram_message,
                follow_up_message=draft.follow_up_message,
                call_opener=draft.call_opener,
            ),
        )
        assert ready.status == "ready"
        assert ready.concept_banner_confirmed is True
        assert ready.noindex_confirmed is True

        sent = service.mark_sent(result.id)
        assert sent.status == "sent"
        assert sent.sent_at is not None
        assert sent.follow_up_due_at is not None
        assert sent.follow_up_due_at > sent.sent_at
        assert session.scalar(select(func.count()).select_from(LeadConceptModel)) == 1


def test_concept_is_shared_by_business_across_result_snapshots() -> None:
    with _session_factory()() as session:
        result = _seed_result(session)
        service = LeadConceptService(session, workspace_id="workspace:first")
        created = service.upsert(
            result.id,
            LeadConceptUpsert(
                concept_type="website_launch",
                feature_highlights=["One-tap call"],
            ),
        )

        repeated = service.find_for_result(result.id)

        assert repeated is not None
        assert repeated.id == created.id
        assert repeated.business_id == result.business_id


def _session_factory():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed_result(session) -> AudienceResultModel:
    now = utcnow()
    product = ProductModel(
        id=new_id("product"),
        workspace_id="workspace:first",
        product_name="Conversion Studio",
        target_customer="Local businesses",
        target_geography="Toronto",
        qualification_criteria=[],
        preferred_discovery_sources=[],
        constraints=[],
        ideal_customer_signals=[],
        exclusions=[],
        offer_summary="Website concepts for local businesses.",
        outreach_objective="Share a personalized concept.",
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
        signal_keys=["website_quality_score"],
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
    result = AudienceResultModel(
        id=new_id("audience_result"),
        run_id=run.id,
        audience_id=audience.id,
        business_id=business.id,
        rank_position=1,
        is_new=True,
        shortlisted_at=now,
        match_snapshot={"title": business.display_name, "raw": {}},
    )
    session.add(result)
    session.commit()
    return result
