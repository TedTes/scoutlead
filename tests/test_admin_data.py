from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from admin.service import AdminDataService
from admin.schemas import (
    AdminBusinessUpdate,
    AdminDataJobCreate,
    AdminSignalDefinitionCreate,
    AdminSignalDefinitionUpdate,
    AdminServiceDefinitionCreate,
    AdminServiceSignalMappingInput,
)
from auth.context import AuthContext
from business_facts.repository import BusinessFactRepository, BusinessFactValue
from db.models import (
    AdminAuditEventModel,
    BusinessFactModel,
    BusinessModel,
    BusinessIndexSegmentModel,
    BusinessNicheMembershipModel,
    FactClaimModel,
    NicheModel,
    QueueJobModel,
    SignalDefinitionModel,
    ServiceDefinitionModel,
    ServiceSignalMappingModel,
    SourceItemModel,
    SourceObservationModel,
    ValidationResultModel,
)
from db.session import create_database
from shared.errors import ConflictError, ValidationError
from shared.utils import new_id, utcnow
from source_items.repository import source_item_content_hash
from source_items.schemas import SourceItemCreate


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _business(session):
    now = utcnow()
    business = BusinessModel(
        id=new_id("business"),
        display_name="Example Painting",
        normalized_name="example painting",
        geography="Toronto",
        market_key="toronto",
        status="active",
        first_seen_at=now,
        last_seen_at=now,
    )
    niche = NicheModel(
        id=new_id("niche"),
        slug="home_service_painting",
        label="Painting",
        active=True,
        signal_vocabulary=[],
    )
    session.add_all([business, niche])
    session.commit()
    return business, niche


def _service(session):
    return AdminDataService(
        session,
        AuthContext(user_id="user_admin", email="admin@example.com"),
    )


def _segment(session, niche):
    segment = BusinessIndexSegmentModel(
        id=new_id("segment"),
        niche_id=niche.id,
        market_key="toronto",
        market_label="Toronto",
        status="active",
        demand_count=1,
        target_business_count=25,
        source_plan=[{"provider_id": "google_places", "query": "painters Toronto"}],
        source_state={},
        next_refresh_at=utcnow(),
    )
    session.add(segment)
    session.commit()
    return segment


def test_edit_quarantines_business_and_audits() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _business(session)

        result = _service(session).update(
            business.id,
            AdminBusinessUpdate(phone="4165550199", reason="Corrected from source profile"),
        )

        audit = session.scalar(select(AdminAuditEventModel))
        assert result["status"] == "quarantined"
        assert audit.action == "update"
        assert audit.actor_email == "admin@example.com"
        assert audit.before["phone"] is None
        assert audit.after["phone"] == "4165550199"


def test_expired_validation_is_reported_as_incomplete() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _business(session)
        now = utcnow()
        for validation_type in ("identity", "business_identity", "trade", "location"):
            session.add(
                ValidationResultModel(
                    id=new_id("validation"),
                    idempotency_key=f"{business.id}:{validation_type}",
                    business_id=business.id,
                    validation_type=validation_type,
                    status="passed",
                    confidence=95,
                    reason="Passed",
                    evidence=[],
                    validator="test",
                    validator_version=1,
                    observed_at=now - timedelta(days=40),
                    expires_at=now - timedelta(days=10),
                )
            )
        session.commit()

        overview = _service(session).overview()

        assert overview["fully_validated"] == 0
        assert overview["incomplete"] == 1


def test_admin_reports_validated_membership_as_searchable() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche = _business(session)
        _segment(session, niche)
        now = utcnow()
        session.add(
            BusinessNicheMembershipModel(
                id=new_id("membership"),
                business_id=business.id,
                niche_id=niche.id,
                market_key="toronto",
                confidence=1.0,
                evidence=[],
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        for validation_type in ("identity", "business_identity", "trade", "location"):
            session.add(
                ValidationResultModel(
                    id=new_id("validation"),
                    idempotency_key=f"{business.id}:{validation_type}:current",
                    business_id=business.id,
                    niche_id=niche.id,
                    market_key="toronto",
                    validation_type=validation_type,
                    status="passed",
                    confidence=95,
                    reason="Passed",
                    evidence=[],
                    validator="test",
                    validator_version=1,
                    observed_at=now,
                    expires_at=now + timedelta(days=30),
                )
            )
        session.commit()

        overview = _service(session).overview()

        assert overview["searchable"] == 1
        assert overview["trade_groups"] == [
            {"slug": niche.slug, "label": niche.label, "count": 1}
        ]


def test_admin_businesses_can_filter_and_sort_by_data_quality_score() -> None:
    factory = _session_factory()
    with factory() as session:
        reliable, niche = _business(session)
        now = utcnow()
        poor = BusinessModel(
            id=new_id("business"),
            display_name="Needs Review Painting",
            normalized_name="needs review painting",
            geography="Toronto",
            market_key="toronto",
            status="active",
            first_seen_at=now,
            last_seen_at=now,
        )
        observation = SourceObservationModel(
            id=new_id("observation"),
            business_id=reliable.id,
            source="google_places",
            external_id="reliable-painting",
            query_signature=None,
            content_hash="q" * 64,
            source_url="https://example.test/reliable",
            raw_payload={"website": "https://example.test"},
            observed_at=now,
        )
        session.add_all([poor, observation])
        session.flush()
        for business in (reliable, poor):
            session.add(
                BusinessNicheMembershipModel(
                    id=new_id("membership"),
                    business_id=business.id,
                    niche_id=niche.id,
                    market_key="toronto",
                    confidence=1.0,
                    evidence=[],
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        for validation_type in ("identity", "business_identity", "trade", "location"):
            session.add(
                ValidationResultModel(
                    id=new_id("validation"),
                    idempotency_key=f"{reliable.id}:{validation_type}:quality-score",
                    business_id=reliable.id,
                    niche_id=niche.id,
                    market_key="toronto",
                    validation_type=validation_type,
                    status="passed",
                    confidence=100,
                    reason="Current evidence passed.",
                    evidence=[],
                    validator="test",
                    validator_version=1,
                    observed_at=now,
                    expires_at=now + timedelta(days=30),
                )
            )
        session.add(
            BusinessFactModel(
                id=new_id("fact"),
                business_id=reliable.id,
                fact_key="website_status",
                value_type="text",
                value_text="present",
                confidence=100,
                resolution_state="confirmed",
                supporting_claim_ids=[],
                quality_state="published",
                quality_policy_version=1,
                observed_at=now,
                expires_at=now + timedelta(days=30),
                source_observation_id=observation.id,
                resolver_version=1,
            )
        )
        session.commit()

        service = _service(session)
        params = {
            "query": None,
            "validation": None,
            "status": None,
            "niche_slug": niche.slug,
            "market_key": None,
            "page": 1,
            "page_size": 50,
        }
        rows = service.list_businesses(**params, quality=None, sort="score_asc")["items"]
        reliable_rows = service.list_businesses(
            **params, quality="reliable", sort="score_desc"
        )["items"]

        assert [(row["display_name"], row["data_quality_score"]) for row in rows] == [
            ("Needs Review Painting", 0),
            ("Example Painting", 100),
        ]
        assert [row["id"] for row in reliable_rows] == [reliable.id]
        assert reliable_rows[0]["data_quality_breakdown"]["fact_count"] == 1

        fact = session.scalar(
            select(BusinessFactModel).where(BusinessFactModel.business_id == reliable.id)
        )
        fact.expires_at = now - timedelta(days=1)
        session.commit()
        degraded = service.list_businesses(
            **params, quality="poor", sort="score_desc"
        )["items"]

        reliable_after_expiry = next(row for row in degraded if row["id"] == reliable.id)
        assert reliable_after_expiry["data_quality_score"] == 64
        assert "Some facts are expired" in reliable_after_expiry[
            "data_quality_breakdown"
        ]["limitations"]


def test_fact_lineage_connects_fact_observation_validation_and_signal() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _business(session)
        now = utcnow()
        definition = SignalDefinitionModel(
            id="signal_contact_form_present",
            key="contact_form_present",
            label="Contact form present",
            value_type="boolean",
            category="conversion",
            status="active",
            collector_key="website_dom",
            extractor_key="contact_form",
            freshness_days=30,
            opportunity_direction="false_is_opportunity",
            config={"minimum_confidence": 90},
            version=1,
        )
        service = ServiceDefinitionModel(
            id="service_lead_capture",
            key="lead_capture",
            label="Lead capture and conversion",
            status="active",
            sort_order=1,
            version=1,
        )
        observation = SourceObservationModel(
            id=new_id("observation"),
            business_id=business.id,
            source="company_website_signal",
            external_id="example-painting/contact",
            query_signature=None,
            content_hash="a" * 64,
            source_url="https://example.test/contact",
            raw_payload={"has_contact_form": False},
            observed_at=now,
        )
        session.add_all([definition, service, observation])
        session.flush()
        mapping = ServiceSignalMappingModel(
            id=new_id("mapping"),
            service_definition_id=service.id,
            signal_definition_id=definition.id,
            weight=1.0,
            sort_order=1,
        )
        claim = FactClaimModel(
            id=new_id("fact_claim"),
            idempotency_key=f"{business.id}:contact-form",
            business_id=business.id,
            fact_key=definition.key,
            signal_definition_id=definition.id,
            value=False,
            source_observation_id=observation.id,
            confidence=95,
            extractor="contact_form",
            extractor_version=1,
            observed_at=now,
            expires_at=now + timedelta(days=30),
        )
        session.add_all([mapping, claim])
        session.flush()
        fact = BusinessFactRepository(session).upsert(
            business.id,
            BusinessFactValue(
                key=definition.key,
                value=False,
                observed_at=now,
                expires_at=now + timedelta(days=30),
                source_observation_id=observation.id,
                supporting_claim_ids=(claim.id,),
                confidence=95,
                quality_state="published",
            ),
        )
        session.add(
            ValidationResultModel(
                id=new_id("validation"),
                idempotency_key=f"{business.id}:signal-contact-form",
                business_id=business.id,
                source_observation_id=observation.id,
                validation_type="signal:contact_form_present",
                status="passed",
                confidence=95,
                reason="Observation reproduces the fact.",
                evidence=[],
                validator="test",
                validator_version=1,
                observed_at=now,
                expires_at=now + timedelta(days=30),
            )
        )
        session.commit()

        result = _service(session).fact_lineage(business.id)

        assert result["business_id"] == business.id
        assert len(result["facts"]) == 1
        lineage_fact = result["facts"][0]
        assert lineage_fact["id"] == fact.id
        assert lineage_fact["source_observation_id"] == observation.id
        assert lineage_fact["supporting_claim_ids"] == [claim.id]
        assert lineage_fact["validation"]["status"] == "passed"
        assert lineage_fact["signal"]["matches_opportunity_value"] is True
        assert lineage_fact["signal"]["eligible_for_matching"] is True
        assert lineage_fact["signal"]["services"][0]["key"] == "lead_capture"
        assert result["claims"][0]["id"] == claim.id
        assert result["observations"][0]["raw_payload"] == {
            "has_contact_form": False
        }

        session.query(ValidationResultModel).delete()
        session.commit()
        without_validation = _service(session).fact_lineage(business.id)
        assert without_validation["facts"][0]["signal"]["eligible_for_matching"] is False


def test_admin_revalidation_makes_passed_business_searchable_without_publication() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche = _business(session)
        segment = _segment(session, niche)
        source_value = SourceItemCreate(
            segment_id=segment.id,
            provider_id="google_places",
            external_id="place-example",
            query="painters Toronto",
            source_url="https://maps.example/example-painting",
            title="Example Painting",
            raw_payload={"primaryTypeDisplayName": "Painter"},
            fetched_at=utcnow(),
        )
        source = SourceItemModel(
            id=new_id("source_item"),
            **source_value.model_dump(),
            content_hash=source_item_content_hash(source_value),
            state="eligible",
            business_id=business.id,
        )
        session.add(source)
        session.commit()

        result = _service(session).revalidate(
            business.id,
            "Refresh the current validation evidence",
        )

        assert result["validation_state"] == "passed"
        assert session.scalar(select(QueueJobModel)) is None


def test_permanent_delete_is_blocked_when_related_records_exist() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche = _business(session)
        segment = _segment(session, niche)
        source_value = SourceItemCreate(
            segment_id=segment.id,
            provider_id="admin_manual",
            external_id=None,
            query="manual",
            source_url="https://example.com/source",
            title=business.display_name,
            raw_payload={},
            fetched_at=utcnow(),
        )
        session.add(
            SourceItemModel(
                id=new_id("source_item"),
                **source_value.model_dump(),
                content_hash=source_item_content_hash(source_value),
                state="eligible",
                business_id=business.id,
            )
        )
        session.commit()

        with pytest.raises(ConflictError):
            _service(session).delete(
                business.id,
                confirmation=business.display_name,
                reason="Duplicate record",
            )


def test_admin_can_queue_review_first_data_job() -> None:
    factory = _session_factory()
    with factory() as session:
        _, niche = _business(session)
        segment = _segment(session, niche)

        result = _service(session).create_data_job(
            AdminDataJobCreate(
                segment_id=segment.id,
                processing_mode="review_first",
                reason="Inspect a new source batch before validation",
            )
        )

        job = session.get(QueueJobModel, result["id"])
        assert result["status"] == "queued"
        assert job is not None
        assert job.payload["admin_requested"] is True
        assert job.payload["processing_mode"] == "review_first"
        assert session.scalar(
            select(AdminAuditEventModel).where(
                AdminAuditEventModel.entity_type == "data_job"
            )
        ).action == "data_job:create"


def test_admin_can_create_update_and_activate_signal_definition() -> None:
    factory = _session_factory()
    with factory() as session:
        service = _service(session)
        created = service.create_signal_definition(
            AdminSignalDefinitionCreate(
                key="primary_cta_present",
                label="Primary CTA present",
                value_type="boolean",
                category="conversion",
                collector_key="website_dom",
                extractor_key="primary_cta",
                freshness_days=30,
                opportunity_direction="false_is_opportunity",
                reason="Add a measurable conversion signal",
            )
        )

        assert created["status"] == "draft"
        updated = service.update_signal_definition(
            created["id"],
            AdminSignalDefinitionUpdate(
                description="A visible primary action is available.",
                reason="Clarify the signal definition",
            ),
        )
        activated = service.change_signal_definition_status(
            created["id"],
            status="active",
            reason="Ready for collection",
        )

        assert updated["version"] == 2
        assert activated["status"] == "active"
        assert session.get(SignalDefinitionModel, created["id"]).status == "active"
        actions = list(
            session.scalars(
                select(AdminAuditEventModel)
                .where(AdminAuditEventModel.entity_type == "signal_definition")
                .order_by(AdminAuditEventModel.created_at)
            )
        )
        assert [event.action for event in actions] == [
            "signal:create",
            "signal:update",
            "signal:status:active",
        ]


def test_admin_creates_service_mapping_and_collects_its_signals() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _business(session)
        signal = SignalDefinitionModel(
            id=new_id("signal"),
            key="html_language_present",
            label="HTML language declared",
            value_type="boolean",
            category="localization",
            status="active",
            collector_key="website_dom",
            extractor_key="html_language_present",
            freshness_days=30,
            opportunity_direction="false_is_opportunity",
            config={},
            version=1,
        )
        session.add(signal)
        session.commit()
        service = _service(session)

        created = service.create_service_definition(
            AdminServiceDefinitionCreate(
                key="multilingual_localization",
                label="Multilingual localization",
                mappings=[
                    AdminServiceSignalMappingInput(
                        signal_definition_id=signal.id,
                        weight=1.5,
                    )
                ],
                reason="Offer localization from measurable website evidence",
            )
        )
        collected = service.collect_service_signals(
            created["id"],
            reason="Backfill localization evidence",
            scope="selected",
            business_ids=[business.id],
            niche_slug=None,
            market_key=None,
            batch_size=25,
        )
        BusinessFactRepository(session).upsert(
            business.id,
            BusinessFactValue(
                key=signal.key,
                value=False,
                observed_at=utcnow(),
                source_observation_id=None,
                quality_state="published",
            ),
        )
        session.commit()
        activated = service.change_service_definition_status(
            created["id"], status="active", reason="Collector is ready"
        )

        assert created["signals"][0]["weight"] == 1.5
        assert activated["status"] == "active"
        assert collected["signal_count"] == 1
        assert len(collected["collection_jobs"]) == 1
        assert session.get(ServiceDefinitionModel, created["id"]).status == "active"


def test_signal_without_collector_cannot_be_activated() -> None:
    factory = _session_factory()
    with factory() as session:
        created = _service(session).create_signal_definition(
            AdminSignalDefinitionCreate(
                key="manual_quality_note",
                label="Manual quality note",
                value_type="text",
                category="quality",
                reason="Prepare a manual review signal",
            )
        )

        with pytest.raises(ValidationError):
            _service(session).change_signal_definition_status(
                created["id"],
                status="active",
                reason="Attempt activation",
            )


def test_activating_signal_queues_selected_business_collection() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _business(session)
        service = _service(session)
        created = service.create_signal_definition(
            AdminSignalDefinitionCreate(
                key="mobile_viewport_present",
                label="Mobile viewport present",
                value_type="boolean",
                category="performance",
                collector_key="existing_observation",
                extractor_key="payload_path",
                config={"payload_path": "website_enrichment.has_mobile_viewport"},
                opportunity_direction="false_is_opportunity",
                reason="Add mobile readiness signal",
            )
        )

        activated = service.change_signal_definition_status(
            created["id"],
            status="active",
            reason="Collect the first business",
            scope="selected",
            business_ids=[business.id],
        )

        assert len(activated["collection_jobs"]) == 1
        job = session.get(QueueJobModel, activated["collection_jobs"][0]["id"])
        assert job.type == "signal.collection"
        assert job.payload["business_ids"] == [business.id]


def test_collect_active_signals_queues_each_definition() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _business(session)
        definitions = [
            SignalDefinitionModel(
                id=new_id("signal"),
                key=key,
                label=label,
                value_type="boolean",
                category="website",
                status="active",
                collector_key="website_dom",
                extractor_key=extractor,
                freshness_days=30,
                opportunity_direction="false_is_opportunity",
                config={"auto_publish": True},
                version=1,
            )
            for key, label, extractor in (
                ("uses_https", "HTTPS enabled", "uses_https"),
                ("mobile_viewport_present", "Mobile viewport present", "mobile_viewport"),
            )
        ]
        session.add_all(definitions)
        session.commit()

        result = _service(session).collect_active_signal_definitions(
            reason="Backfill website quality signals",
            scope="selected",
            business_ids=[business.id],
            niche_slug=None,
            market_key=None,
            batch_size=100,
        )

        assert result["definition_count"] == 2
        assert result["job_count"] == 2
        jobs = list(session.scalars(select(QueueJobModel)))
        assert {job.payload["signal_definition_id"] for job in jobs} == {
            definition.id for definition in definitions
        }


def test_business_detail_reports_current_and_missing_signal_coverage() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _business(session)
        now = utcnow()
        current = SignalDefinitionModel(
            id=new_id("signal"),
            key="mobile_viewport_present",
            label="Mobile viewport present",
            value_type="boolean",
            category="performance",
            status="active",
            collector_key="website_dom",
            extractor_key="payload_path",
            freshness_days=30,
            opportunity_direction="false_is_opportunity",
            config={"payload_path": "website_enrichment.has_mobile_viewport"},
            version=1,
        )
        missing = SignalDefinitionModel(
            id=new_id("signal"),
            key="domain_age_days",
            label="Domain age",
            value_type="number",
            category="website",
            unit="days",
            status="active",
            collector_key="existing_observation",
            extractor_key="payload_path",
            freshness_days=90,
            opportunity_direction="none",
            config={"payload_path": "domain.age_days"},
            version=1,
        )
        session.add_all([current, missing])
        session.flush()
        session.add(
            BusinessFactModel(
                id=new_id("fact"),
                business_id=business.id,
                fact_key=current.key,
                signal_definition_id=current.id,
                value_type="boolean",
                value_boolean=True,
                confidence=95,
                resolution_state="resolved",
                supporting_claim_ids=[],
                quality_state="published",
                quality_policy_version=1,
                observed_at=now,
                expires_at=now + timedelta(days=30),
                resolver_version=1,
            )
        )
        session.commit()

        signals = {
            signal["key"]: signal
            for signal in _service(session).detail(business.id)["signals"]
        }

        assert signals["mobile_viewport_present"]["status"] == "current"
        assert signals["mobile_viewport_present"]["value"] is True
        assert signals["domain_age_days"]["status"] == "missing"


def test_admin_approval_publishes_only_selected_staged_signal_fact() -> None:
    factory = _session_factory()
    with factory() as session:
        first, _ = _business(session)
        second = BusinessModel(
            id=new_id("business"),
            display_name="Second Painting",
            normalized_name="second painting",
            geography="Toronto",
            market_key="toronto",
            status="active",
            first_seen_at=utcnow(),
            last_seen_at=utcnow(),
        )
        definition = SignalDefinitionModel(
            id=new_id("signal"),
            key="mobile_viewport_present",
            label="Mobile viewport present",
            value_type="boolean",
            category="performance",
            status="active",
            collector_key="website_dom",
            extractor_key="payload_path",
            freshness_days=30,
            opportunity_direction="false_is_opportunity",
            config={},
            version=1,
        )
        session.add_all([second, definition])
        session.flush()
        facts = []
        for business in (first, second):
            fact = BusinessFactModel(
                id=new_id("fact"),
                business_id=business.id,
                fact_key=definition.key,
                signal_definition_id=definition.id,
                value_type="boolean",
                value_boolean=False,
                confidence=100,
                resolution_state="confirmed",
                supporting_claim_ids=[],
                quality_state="staged",
                quality_policy_version=1,
                observed_at=utcnow(),
                resolver_version=1,
            )
            session.add(fact)
            facts.append(fact)
        session.commit()

        result = _service(session).validate_signal_facts(
            definition.id,
            decision="approve",
            reason="Evidence inspected for the selected business",
            scope="selected",
            business_ids=[first.id],
        )

        assert result["affected_count"] == 1
        assert facts[0].quality_state == "published"
        assert facts[1].quality_state == "staged"


def test_review_first_batch_only_enters_pipeline_after_admin_approval() -> None:
    factory = _session_factory()
    with factory() as session:
        _, niche = _business(session)
        segment = _segment(session, niche)
        service = _service(session)
        root_summary = service.create_data_job(
            AdminDataJobCreate(
                segment_id=segment.id,
                processing_mode="review_first",
                reason="Review before validation",
            )
        )
        root = session.get(QueueJobModel, root_summary["id"])
        root.status = "completed"
        root.completed_at = utcnow()
        child = QueueJobModel(
            id=new_id("job"),
            type="source.fetch",
            payload={
                "segment_id": segment.id,
                "source_index": 0,
                "processing_mode": "review_first",
            },
            status="completed",
            attempts=1,
            max_attempts=3,
            run_after=utcnow(),
            parent_run_id=root.id,
            completed_at=utcnow(),
        )
        session.add(child)
        session.flush()
        source_value = SourceItemCreate(
            segment_id=segment.id,
            job_id=child.id,
            provider_id="google_places",
            external_id="place-1",
            query="painters Toronto",
            source_url="https://maps.example/place-1",
            title="Example Painter",
            raw_payload={"address": "Toronto", "phone": "4165550100"},
            fetched_at=utcnow(),
        )
        source = SourceItemModel(
            id=new_id("source_item"),
            **source_value.model_dump(),
            content_hash=source_item_content_hash(source_value),
            state="fetched",
        )
        session.add(source)
        session.commit()

        before = service.data_job_detail(root.id)
        assert before["status"] == "awaiting_review"
        assert before["pending_review"] == 1
        assert source.business_id is None

        after = service.validate_data_job(
            root.id,
            reason="The source sample has sufficient identity fields",
            source_item_ids=[source.id],
        )

        queued = session.scalar(
            select(QueueJobModel).where(QueueJobModel.type == "business.identity_resolve")
        )
        assert queued is not None
        assert queued.payload["source_item_id"] == source.id
        assert source.business_id is None
        assert source.state == "resolution_queued"
        assert after["review_state"] == "approved"
