from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import BusinessIndexSegmentModel, NicheModel, ProductModel, QueueJobModel
from db.session import create_database
from shared.utils import utcnow
from source_items.repository import SourceItemRepository
from source_items.schemas import (
    SourceItemCreate,
    SourceItemDecisionCreate,
    SourceItemDecisionValue,
    SourceItemReview,
    SourceItemReviewAction,
    SourceItemStage,
    SourceItemState,
)
from source_items.service import SourceItemReviewService


def test_repeated_fetches_create_distinct_immutable_source_items() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_segment(session)
        repository = SourceItemRepository(session)
        value = SourceItemCreate(
            segment_id="segment_test",
            job_id=None,
            provider_id="configured_search",
            external_id="result-1",
            query="painters in Toronto",
            source_url="https://example.test/listing/1",
            title="Example Painter",
            raw_payload={"description": "Residential painting service"},
            fetched_at=utcnow(),
        )

        first = repository.ingest(value)
        repeated = repository.ingest(value)

        assert first.id != repeated.id
        assert first.content_hash == repeated.content_hash
        assert first.state == SourceItemState.FETCHED.value
        assert first.business_id is None
        SourceItemReviewService(session).review(
            first.id,
            SourceItemReview(action=SourceItemReviewAction.REJECT),
            actor_id="reviewer-1",
        )
        prior = repository.latest_user_decision_for(repeated)
        assert prior is not None
        assert prior.decision == SourceItemDecisionValue.REJECTED.value


def test_source_item_decisions_are_append_only_and_update_current_state() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_segment(session)
        repository = SourceItemRepository(session)
        item = repository.ingest(
            SourceItemCreate(
                segment_id="segment_test",
                provider_id="apify/kijiji",
                query="house painters Toronto",
                source_url="https://kijiji.example/item/1",
                title="Home Painting Services",
                raw_payload={"seller": {"name": "Pro Paints"}},
                fetched_at=utcnow(),
            )
        )

        repository.add_decision(
            item.id,
            SourceItemDecisionCreate(
                stage=SourceItemStage.RELEVANCE,
                decision=SourceItemDecisionValue.NEEDS_REVIEW,
                reason=(
                    "Marketplace listing has a business seller but incomplete identity evidence."
                ),
                confidence=61,
            ),
            next_state=SourceItemState.NEEDS_REVIEW,
        )
        repository.add_decision(
            item.id,
            SourceItemDecisionCreate(
                stage=SourceItemStage.RELEVANCE,
                decision=SourceItemDecisionValue.ACCEPTED,
                reason="Confirmed by reviewer.",
                actor_type="user",
                actor_id="user_test",
            ),
            next_state=SourceItemState.RELEVANT,
        )

        refreshed = repository.get(item.id)
        assert refreshed.state == SourceItemState.RELEVANT.value
        assert [decision.decision for decision in refreshed.decisions] == [
            SourceItemDecisionValue.NEEDS_REVIEW.value,
            SourceItemDecisionValue.ACCEPTED.value,
        ]


def test_human_review_is_versioned_and_overrides_current_state() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_segment(session)
        repository = SourceItemRepository(session)
        item = repository.ingest(
            SourceItemCreate(
                segment_id="segment_test",
                provider_id="configured_search",
                query="painters Toronto",
                title="Painter listing",
                raw_payload={"snippet": "Local painting service"},
                fetched_at=utcnow(),
            )
        )

        reviewed = SourceItemReviewService(session).review(
            item.id,
            SourceItemReview(
                action=SourceItemReviewAction.ACCEPT,
                reason="Confirmed as a local painting business.",
            ),
            actor_id="user_test",
        )

        assert reviewed.state == SourceItemState.RELEVANT.value
        assert reviewed.decisions[-1].actor_type == "user"
        assert reviewed.decisions[-1].reason == "Confirmed as a local painting business."
        queued = session.query(QueueJobModel).one()
        assert queued.type == "business.identity_resolve"
        assert queued.payload["source_item_id"] == item.id


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _add_segment(session) -> None:
    now = utcnow()
    session.add(
        ProductModel(
            id="product_test",
            workspace_id=None,
            product_name="Website growth",
            product_description=None,
            target_customer="Painters",
            problem_being_solved=None,
            value_proposition=None,
            target_geography="Toronto",
            validation_goal=None,
            qualification_criteria=[],
            preferred_discovery_sources=[],
            outreach_objective=None,
            constraints=[],
            offer_summary=None,
            ideal_customer_signals=[],
            exclusions=[],
            typical_deal_value=None,
        )
    )
    session.add(
        NicheModel(
            id="niche_test",
            slug="painters",
            label="Painters",
            category="painting contractor",
            active=True,
            signal_vocabulary=[],
        )
    )
    session.flush()
    session.add(
        BusinessIndexSegmentModel(
            id="segment_test",
            niche_id="niche_test",
            product_id="product_test",
            market_key="toronto",
            market_label="Toronto",
            status="active",
            demand_count=1,
            target_business_count=25,
            source_plan=[],
            source_state={},
            next_refresh_at=now,
        )
    )
    session.commit()
