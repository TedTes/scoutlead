from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, delete as sql_delete, exists, func, or_, select
from sqlalchemy.orm import Session

from admin.schemas import (
    AdminBusinessCreate,
    AdminBusinessUpdate,
    AdminDataJobCreate,
    AdminServiceDefinitionCreate,
    AdminServiceDefinitionUpdate,
    AdminSignalDefinitionCreate,
    AdminSignalDefinitionUpdate,
)
from auth.context import AuthContext
from business_attributes.catalog import (
    ATTRIBUTE_GROUP_BY_KEY,
    ATTRIBUTE_SORT_ORDER,
    TRACKED_ATTRIBUTE_KEYS,
)
from business_attributes.attribute_scoring import audience_match_config, score_attribute
from business_attributes.eligibility import (
    DEFAULT_MINIMUM_FACT_CONFIDENCE,
    eligible_fact_condition,
)
from business_index.eligibility import searchable_business_conditions
from canonical.normalization import normalize_business_name, normalize_domain, normalize_phone
from db.base import Base
from db.models import (
    AdminAuditEventModel,
    BusinessAttributeModel,
    BusinessIndexSegmentModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    ContactModel,
    NicheModel,
    QueueJobModel,
    ServiceDefinitionModel,
    ServiceSignalMappingModel,
    SignalDefinitionModel,
    SourceItemModel,
)
from outreach_packages.playbooks import ServicePlaybook
from outreach_packages.repository import OutreachPlaybookRepository
from job_queue.schemas import JobStatus, JobType
from job_queue.service import QueueService
from shared.errors import ConflictError, NotFoundError, ValidationError
from shared.utils import new_id, normalize_url, utcnow
from service_definitions.repository import ServiceDefinitionRepository
from seeding.batches import active_membership_condition
from signal_definitions.repository import SignalDefinitionRepository
from source_items.repository import SourceItemRepository, source_item_content_hash
from source_items.schemas import (
    SourceItemCreate,
    SourceItemDecisionCreate,
    SourceItemDecisionValue,
    SourceItemStage,
    SourceItemState,
)


SOURCE_PRIORITY = {
    "google_places": 0,
    "google_places_seed": 1,
    "company_website_seed": 2,
    "openstreetmap_seed": 3,
    "configured_search": 4,
    "website_presence_check": 5,
    "admin_manual": 6,
}

MATCH_ATTRIBUTE_LABELS = {
    "website_status": "Website missing",
    "http_status": "Website unavailable",
    "mobile_viewport_present": "No mobile viewport",
    "website_quality_score": "Website needs upgrade",
    "performance_score": "Low PageSpeed performance",
    "accessibility_score": "Low accessibility score",
    "best_practices_score": "Low best-practices score",
    "contact_form_present": "No contact form",
    "quote_or_booking_form_present": "No quote or booking flow",
    "primary_cta_present": "No primary call to action",
    "click_to_call_present": "No click-to-call",
    "public_email_present": "No public email",
    "public_phone_present": "No public phone",
    "google_rating": "Low Google rating",
    "google_review_count": "Low review count",
    "review_recency_days": "Stale reviews",
    "google_business_profile_present": "No Google Business Profile",
    "local_business_schema_present": "No local-business schema",
    "service_area_content_present": "No service-area content",
    "title_and_meta_present": "Missing title or meta description",
}

OPPORTUNITY_GROUPS = {
    "website_status": ("website_missing", "Website missing"),
    "http_status": ("website_upgrade", "Website needs upgrade"),
    "mobile_viewport_present": ("website_upgrade", "Website needs upgrade"),
    "website_quality_score": ("website_upgrade", "Website needs upgrade"),
    "performance_score": ("website_upgrade", "Website needs upgrade"),
    "accessibility_score": ("website_upgrade", "Website needs upgrade"),
    "best_practices_score": ("website_upgrade", "Website needs upgrade"),
    # Conversion findings are component evidence for the one customer-facing
    # website-upgrade opportunity. They remain individually visible so an
    # administrator can tell exactly why the composite outcome was produced.
    "contact_form_present": ("website_upgrade", "Website needs improvement"),
    "quote_or_booking_form_present": ("website_upgrade", "Website needs improvement"),
    "primary_cta_present": ("website_upgrade", "Website needs improvement"),
    "click_to_call_present": ("website_upgrade", "Website needs improvement"),
    "google_rating": ("reputation", "Reputation gap"),
    "google_review_count": ("reputation", "Reputation gap"),
}

ESTIMATED_NO_WEBSITE_SCORE = 85.0
ESTIMATED_WEBSITE_UPGRADE_SCORE = 65.0
ESTIMATED_ELIGIBILITY_FACTOR = 0.8


class AdminDataService:
    def __init__(self, session: Session, auth: AuthContext) -> None:
        self.session = session
        self.auth = auth

    def list_signal_definitions(self, *, status: str | None = None) -> list[dict[str, Any]]:
        if status and status not in {"draft", "active", "inactive"}:
            raise ValidationError("Unknown signal status", {"status": status})
        return [
            _signal_definition_dict(definition)
            for definition in SignalDefinitionRepository(self.session).list(status=status)
        ]

    def list_service_definitions(self, *, status: str | None = None) -> list[dict[str, Any]]:
        if status and status not in {"draft", "active", "inactive"}:
            raise ValidationError("Unknown service status", {"status": status})
        return [
            _service_definition_dict(service)
            for service in ServiceDefinitionRepository(self.session).list(status=status)
        ]

    def list_outreach_playbooks(self):
        return OutreachPlaybookRepository(self.session).list()

    def update_outreach_playbook(
        self,
        service_key: str,
        *,
        definition: dict[str, Any],
        reason: str,
    ):
        repository = OutreachPlaybookRepository(self.session)
        existing = repository.get_row(service_key)
        before = dict(existing.definition) if existing else None
        try:
            ServicePlaybook.model_validate(definition)
            row = repository.save(service_key=service_key, definition=definition)
        except (ValueError, TypeError) as exc:
            raise ValidationError(
                "Invalid outreach playbook definition",
                {"service_key": service_key, "error": str(exc)},
            ) from exc
        after = dict(row.definition)
        self._audit(
            "outreach_playbook:update",
            row.id,
            reason,
            before,
            after,
            entity_type="outreach_playbook",
        )
        self.session.commit()
        return next(
            item
            for item in repository.list()
            if item.service_key == service_key
        )

    def change_outreach_playbook_status(
        self,
        service_key: str,
        *,
        status: str,
        reason: str,
    ):
        if status not in {"draft", "active", "inactive"}:
            raise ValidationError("Unknown playbook status", {"status": status})
        repository = OutreachPlaybookRepository(self.session)
        row = repository.get_row(service_key)
        if row is None:
            default = next(
                (
                    item
                    for item in repository.list()
                    if item.service_key == service_key
                ),
                None,
            )
            if default is None:
                raise NotFoundError("outreach playbook not found", {"service_key": service_key})
            row = repository.save(service_key=service_key, definition=default.definition)
        before = {"status": row.status, "version": row.version}
        row.status = status
        row.version += 1
        self._audit(
            f"outreach_playbook:status:{status}",
            row.id,
            reason,
            before,
            {"status": row.status, "version": row.version},
            entity_type="outreach_playbook",
        )
        self.session.commit()
        return next(
            item
            for item in repository.list()
            if item.service_key == service_key
        )

    def create_service_definition(
        self,
        data: AdminServiceDefinitionCreate,
    ) -> dict[str, Any]:
        repository = ServiceDefinitionRepository(self.session)
        if repository.get_by_key(data.key) is not None:
            raise ConflictError("Service key already exists", {"key": data.key})
        mappings = self._service_mappings(data.mappings)
        service = ServiceDefinitionModel(
            id=new_id("service"),
            key=data.key,
            label=data.label,
            description=data.description,
            status="draft",
            sort_order=data.sort_order,
            version=1,
        )
        self.session.add(service)
        self.session.flush()
        for index, (signal, weight) in enumerate(mappings):
            self.session.add(
                ServiceSignalMappingModel(
                    id=new_id("service_signal"),
                    service_definition_id=service.id,
                    signal_definition_id=signal.id,
                    weight=weight,
                    sort_order=index,
                )
            )
        self.session.flush()
        created = repository.get(service.id)
        assert created is not None
        after = _service_definition_dict(created)
        self._audit(
            "service:create",
            service.id,
            data.reason,
            None,
            after,
            entity_type="service_definition",
        )
        self.session.commit()
        return after

    def update_service_definition(
        self,
        service_id: str,
        data: AdminServiceDefinitionUpdate,
    ) -> dict[str, Any]:
        repository = ServiceDefinitionRepository(self.session)
        service = repository.get(service_id)
        if service is None:
            raise NotFoundError("service definition not found", {"service_id": service_id})
        before = _service_definition_dict(service)
        values = data.model_dump(exclude_unset=True, exclude={"reason", "mappings"})
        for key, value in values.items():
            setattr(service, key, value)
        if data.mappings is not None:
            replacements = self._service_mappings(data.mappings)
            service.signal_mappings.clear()
            self.session.flush()
            for index, (signal, weight) in enumerate(replacements):
                service.signal_mappings.append(
                    ServiceSignalMappingModel(
                        id=new_id("service_signal"),
                        signal_definition_id=signal.id,
                        weight=weight,
                        sort_order=index,
                    )
                )
            if service.status == "active":
                service.status = "draft"
        service.version += 1
        self.session.flush()
        updated = repository.get(service.id)
        assert updated is not None
        after = _service_definition_dict(updated)
        self._audit(
            "service:update",
            service.id,
            data.reason,
            before,
            after,
            entity_type="service_definition",
        )
        self.session.commit()
        return after

    def change_service_definition_status(
        self,
        service_id: str,
        *,
        status: str,
        reason: str,
    ) -> dict[str, Any]:
        if status not in {"draft", "active", "inactive"}:
            raise ValidationError("Unknown service status", {"status": status})
        repository = ServiceDefinitionRepository(self.session)
        service = repository.get(service_id)
        if service is None:
            raise NotFoundError("service definition not found", {"service_id": service_id})
        if status == "active":
            active_mappings = [
                mapping
                for mapping in service.signal_mappings
                if mapping.signal_definition.status == "active"
                and mapping.signal_definition.opportunity_direction != "none"
            ]
            if not active_mappings:
                raise ValidationError(
                    "Active services require at least one active opportunity signal",
                    {"service_id": service_id},
                )
            uncovered = [
                mapping.signal_definition.key
                for mapping in active_mappings
                if not self.session.scalar(
                    select(BusinessAttributeModel.id)
                    .where(
                        BusinessAttributeModel.signal_definition_id
                        == mapping.signal_definition_id,
                        BusinessAttributeModel.row_type == "attribute",
                        BusinessAttributeModel.resolution_state == "confirmed",
                    )
                    .limit(1)
                )
            ]
            if uncovered:
                raise ValidationError(
                    "Collect and validate every mapped signal before activating the service",
                    {"signal_keys": uncovered},
                )
        before = _service_definition_dict(service)
        service.status = status
        service.version += 1
        self.session.flush()
        after = _service_definition_dict(service)
        self._audit(
            f"service:status:{status}",
            service.id,
            reason,
            before,
            after,
            entity_type="service_definition",
        )
        self.session.commit()
        return after

    def collect_service_signals(
        self,
        service_id: str,
        *,
        reason: str,
        scope: str,
        business_ids: list[str],
        niche_slug: str | None,
        market_key: str | None,
        batch_size: int,
    ) -> dict[str, Any]:
        service = ServiceDefinitionRepository(self.session).get(service_id)
        if service is None:
            raise NotFoundError("service definition not found", {"service_id": service_id})
        if service.status == "inactive":
            raise ConflictError("Inactive services cannot collect signals")
        jobs: list[dict[str, Any]] = []
        signal_ids: list[str] = []
        for mapping in sorted(service.signal_mappings, key=lambda item: item.sort_order):
            definition = mapping.signal_definition
            if definition.status != "active":
                continue
            signal_ids.append(definition.id)
            jobs.extend(
                self._enqueue_signal_collection(
                    definition,
                    reason=reason,
                    scope=scope,
                    business_ids=business_ids,
                    niche_slug=niche_slug,
                    market_key=market_key,
                    batch_size=batch_size,
                )
            )
        self._audit(
            "service:collect",
            service.id,
            reason,
            None,
            {"scope": scope, "signal_ids": signal_ids, "job_ids": [job["id"] for job in jobs]},
            entity_type="service_definition",
        )
        self.session.commit()
        return {
            "service": _service_definition_dict(service),
            "signal_count": len(signal_ids),
            "collection_jobs": jobs,
        }

    def _service_mappings(self, mappings) -> list[tuple[SignalDefinitionModel, float]]:
        seen: set[str] = set()
        resolved: list[tuple[SignalDefinitionModel, float]] = []
        for mapping in mappings:
            if mapping.signal_definition_id in seen:
                continue
            signal = self.session.get(SignalDefinitionModel, mapping.signal_definition_id)
            if signal is None:
                raise ValidationError(
                    "Service mapping references an unknown signal",
                    {"signal_definition_id": mapping.signal_definition_id},
                )
            seen.add(signal.id)
            resolved.append((signal, mapping.weight))
        return resolved

    def create_signal_definition(
        self,
        data: AdminSignalDefinitionCreate,
    ) -> dict[str, Any]:
        repository = SignalDefinitionRepository(self.session)
        if repository.get_by_key(data.key) is not None:
            raise ConflictError("A signal with this key already exists", {"key": data.key})
        definition = SignalDefinitionModel(
            id=new_id("signal"),
            **data.model_dump(exclude={"reason"}),
            status="draft",
            version=1,
        )
        self.session.add(definition)
        self.session.flush()
        after = _signal_definition_dict(definition)
        self._audit(
            "signal:create",
            definition.id,
            data.reason,
            None,
            after,
            entity_type="signal_definition",
        )
        self.session.commit()
        return after

    def update_signal_definition(
        self,
        signal_id: str,
        data: AdminSignalDefinitionUpdate,
    ) -> dict[str, Any]:
        definition = self._signal_definition(signal_id)
        before = _signal_definition_dict(definition)
        updates = data.model_dump(exclude={"reason"}, exclude_unset=True)
        for field, value in updates.items():
            setattr(definition, field, value)
        definition.version += 1
        after = _signal_definition_dict(definition)
        self._audit(
            "signal:update",
            definition.id,
            data.reason,
            before,
            after,
            entity_type="signal_definition",
        )
        self.session.commit()
        return after

    def change_signal_definition_status(
        self,
        signal_id: str,
        *,
        status: str,
        reason: str,
        scope: str = "all",
        business_ids: list[str] | None = None,
        niche_slug: str | None = None,
        market_key: str | None = None,
        batch_size: int = 25,
    ) -> dict[str, Any]:
        definition = self._signal_definition(signal_id)
        if status == "active" and (not definition.collector_key or not definition.extractor_key):
            raise ValidationError(
                "Active signals require a collector and extractor",
                {"signal_id": signal_id},
            )
        if status == "active":
            self._validate_signal_definition(definition)
        before = _signal_definition_dict(definition)
        definition.status = status
        after = _signal_definition_dict(definition)
        self._audit(
            f"signal:status:{status}",
            definition.id,
            reason,
            before,
            after,
            entity_type="signal_definition",
        )
        jobs = []
        if status == "active":
            jobs = self._enqueue_signal_collection(
                definition,
                reason=reason,
                scope=scope,
                business_ids=business_ids or [],
                niche_slug=niche_slug,
                market_key=market_key,
                batch_size=batch_size,
            )
        self.session.commit()
        return {**after, "collection_jobs": jobs}

    def collect_signal_definition(
        self,
        signal_id: str,
        *,
        reason: str,
        scope: str,
        business_ids: list[str],
        niche_slug: str | None,
        market_key: str | None,
        batch_size: int,
    ) -> dict[str, Any]:
        definition = self._signal_definition(signal_id)
        if definition.status != "active":
            raise ConflictError("Only active signals can be collected")
        jobs = self._enqueue_signal_collection(
            definition,
            reason=reason,
            scope=scope,
            business_ids=business_ids,
            niche_slug=niche_slug,
            market_key=market_key,
            batch_size=batch_size,
        )
        self._audit(
            "signal:collect",
            definition.id,
            reason,
            None,
            {"scope": scope, "job_ids": [job["id"] for job in jobs]},
            entity_type="signal_definition",
        )
        self.session.commit()
        return {"signal": _signal_definition_dict(definition), "collection_jobs": jobs}

    def collect_active_signal_definitions(
        self,
        *,
        reason: str,
        scope: str,
        business_ids: list[str],
        niche_slug: str | None,
        market_key: str | None,
        batch_size: int,
    ) -> dict[str, Any]:
        definitions = SignalDefinitionRepository(self.session).list(status="active")
        jobs: list[dict[str, Any]] = []
        for definition in definitions:
            definition_jobs = self._enqueue_signal_collection(
                definition,
                reason=reason,
                scope=scope,
                business_ids=business_ids,
                niche_slug=niche_slug,
                market_key=market_key,
                batch_size=batch_size,
            )
            jobs.extend(
                {**job, "signal_definition_id": definition.id, "signal_key": definition.key}
                for job in definition_jobs
            )
        self._audit(
            "signal:collect-active",
            "active-signals",
            reason,
            None,
            {
                "scope": scope,
                "definition_count": len(definitions),
                "job_ids": [job["id"] for job in jobs],
            },
            entity_type="signal_definition",
        )
        self.session.commit()
        return {"definition_count": len(definitions), "job_count": len(jobs), "collection_jobs": jobs}

    def validate_signal_facts(
        self,
        signal_id: str,
        *,
        decision: str,
        reason: str,
        scope: str,
        business_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        definition = self._signal_definition(signal_id)
        if decision not in {"approve", "reject"}:
            raise ValidationError("Unknown signal validation decision")
        if scope not in {"all", "selected"}:
            raise ValidationError("Unknown signal validation scope", {"scope": scope})
        selected_ids = list(dict.fromkeys(business_ids or []))
        if scope == "selected" and not selected_ids:
            raise ValidationError("Selected scope requires at least one business")
        statement = select(BusinessAttributeModel).where(
            BusinessAttributeModel.signal_definition_id == definition.id,
            BusinessAttributeModel.row_type == "attribute",
        )
        if scope == "selected":
            statement = statement.where(BusinessAttributeModel.business_id.in_(selected_ids))
        facts = list(self.session.scalars(statement))
        for fact in facts:
            fact.resolution_state = "confirmed" if decision == "approve" else "rejected"
        affected_ids = [fact.business_id for fact in facts]
        self._audit(
            f"signal:validate:{decision}",
            definition.id,
            reason,
            None,
            {
                "scope": scope,
                "affected_count": len(facts),
                "business_ids": affected_ids[:100],
            },
            entity_type="signal_definition",
        )
        self.session.commit()
        return {
            "signal": _signal_definition_dict(definition),
            "decision": decision,
            "affected_count": len(facts),
            "business_ids": affected_ids,
        }

    def list_data_segments(self) -> list[dict[str, Any]]:
        rows = self.session.execute(
            select(BusinessIndexSegmentModel, NicheModel)
            .join(NicheModel, NicheModel.id == BusinessIndexSegmentModel.niche_id)
            .order_by(NicheModel.label, BusinessIndexSegmentModel.market_label)
        )
        return [
            {
                "id": segment.id,
                "niche_slug": niche.slug,
                "niche_label": niche.label,
                "market_key": segment.market_key,
                "market_label": segment.market_label,
                "status": segment.status,
                "source_count": len(segment.source_plan or []),
                "target_business_count": segment.target_business_count,
            }
            for segment, niche in rows
        ]

    def list_data_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        roots = list(
            self.session.scalars(
                select(QueueJobModel)
                .where(QueueJobModel.type == JobType.BUSINESS_INDEX_REFRESH.value)
                .order_by(QueueJobModel.created_at.desc())
                .limit(max(limit * 5, limit))
            )
        )
        admin_roots = [job for job in roots if (job.payload or {}).get("admin_requested")]
        return [self._data_job_summary(job) for job in admin_roots[:limit]]

    def create_data_job(self, data: AdminDataJobCreate) -> dict[str, Any]:
        segment = self.session.get(BusinessIndexSegmentModel, data.segment_id)
        if segment is None:
            raise NotFoundError("business index segment not found", {"segment_id": data.segment_id})
        if segment.status != "active":
            raise ConflictError("Only active business index segments can be refreshed")
        active_jobs = list(
            self.session.scalars(
                select(QueueJobModel).where(
                    QueueJobModel.type.in_([
                        JobType.BUSINESS_INDEX_REFRESH.value,
                        JobType.SOURCE_FETCH.value,
                    ]),
                    QueueJobModel.status.in_([
                        JobStatus.QUEUED.value,
                        JobStatus.RUNNING.value,
                    ]),
                )
            )
        )
        if any(str((job.payload or {}).get("segment_id")) == segment.id for job in active_jobs):
            raise ConflictError("This segment already has collection work in progress")
        job = QueueService(self.session).enqueue_business_index_refresh(
            segment_id=segment.id,
            processing_mode=data.processing_mode,
            admin_requested=True,
            requested_by=self.auth.user_id,
            reason=data.reason,
        )
        self._audit(
            "data_job:create",
            job.id,
            data.reason,
            None,
            {"segment_id": segment.id, "processing_mode": data.processing_mode},
            entity_type="data_job",
        )
        self.session.commit()
        return self._data_job_summary(job)

    def data_job_detail(self, job_id: str) -> dict[str, Any]:
        return self._data_job_summary(self._data_job(job_id), include_samples=True)

    def validate_data_job(
        self,
        job_id: str,
        *,
        reason: str,
        sample_size: int | None = None,
        source_item_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        root = self._data_job(job_id)
        if (root.payload or {}).get("processing_mode") != "review_first":
            raise ConflictError("Automatic jobs do not have a manual validation gate")
        children, items = self._data_job_records(root)
        if any(job.status in {JobStatus.QUEUED.value, JobStatus.RUNNING.value} for job in children):
            raise ConflictError("Collection must finish before indexing can start")
        eligible = [
            item for item in items
            if item.business_id is None
            and item.state in {SourceItemState.FETCHED.value, SourceItemState.RELEVANT.value}
        ]
        eligible.sort(key=lambda item: (item.provider_id, item.fetched_at, item.id))
        requested_ids = set(source_item_ids or [])
        if requested_ids:
            batch_ids = {item.id for item in items}
            unknown_ids = requested_ids - batch_ids
            if unknown_ids:
                raise ValidationError(
                    "One or more selected source items do not belong to this fetch",
                    {"source_item_ids": sorted(unknown_ids)},
                )
            eligible_by_id = {item.id: item for item in eligible}
            unavailable_ids = requested_ids - set(eligible_by_id)
            if unavailable_ids:
                raise ConflictError(
                    "One or more selected source items have already been processed",
                    {"source_item_ids": sorted(unavailable_ids)},
                )
            selected = [eligible_by_id[item_id] for item_id in source_item_ids or []]
        else:
            selected = eligible[:sample_size] if sample_size else eligible
        if not selected:
            raise ConflictError("This batch has no unprocessed source items")
        queue = QueueService(self.session)
        for item in selected:
            item.state = SourceItemState.RESOLUTION_QUEUED.value
            queue.enqueue_business_identity_resolve(
                source_item_id=item.id,
                segment_id=item.segment_id,
            )
        remaining = len(eligible) - len(selected)
        root.payload = {
            **(root.payload or {}),
            "review_state": "sample_processing" if remaining else "approved",
            "reviewed_at": utcnow().isoformat(),
            "reviewed_by": self.auth.user_id,
            "approved_count": int((root.payload or {}).get("approved_count", 0)) + len(selected),
        }
        self._audit(
            (
                "data_job:validate_selected"
                if requested_ids
                else "data_job:validate_sample"
                if remaining
                else "data_job:validate_all"
            ),
            root.id,
            reason,
            None,
            {"queued_count": len(selected), "remaining_count": remaining},
            entity_type="data_job",
        )
        self.session.commit()
        return self._data_job_summary(root, include_samples=True)

    def discard_data_job(self, job_id: str, *, reason: str) -> dict[str, Any]:
        root = self._data_job(job_id)
        if (root.payload or {}).get("processing_mode") != "review_first":
            raise ConflictError("Only review-first jobs can discard staged source items")
        children, items = self._data_job_records(root)
        if any(job.status in {JobStatus.QUEUED.value, JobStatus.RUNNING.value} for job in children):
            raise ConflictError("Collection must finish before staged items can be discarded")
        repository = SourceItemRepository(self.session)
        pending = [
            item for item in items
            if item.business_id is None
            and item.state in {SourceItemState.FETCHED.value, SourceItemState.RELEVANT.value}
        ]
        for item in pending:
            repository.add_decision(
                item.id,
                SourceItemDecisionCreate(
                    stage=SourceItemStage.RELEVANCE,
                    decision=SourceItemDecisionValue.REJECTED,
                    reason=reason,
                    actor_type="user",
                    actor_id=self.auth.user_id,
                    details={"admin_batch_discard": root.id},
                ),
                next_state=SourceItemState.REJECTED,
                commit=False,
            )
        root.payload = {
            **(root.payload or {}),
            "review_state": "discarded",
            "reviewed_at": utcnow().isoformat(),
            "reviewed_by": self.auth.user_id,
        }
        self._audit(
            "data_job:discard",
            root.id,
            reason,
            None,
            {"discarded_count": len(pending)},
            entity_type="data_job",
        )
        self.session.commit()
        return self._data_job_summary(root, include_samples=True)

    def cancel_data_job(self, job_id: str, *, reason: str) -> dict[str, Any]:
        root = self._data_job(job_id)
        children, _ = self._data_job_records(root)
        jobs = [root, *children]
        if any(job.status == JobStatus.RUNNING.value for job in jobs):
            raise ConflictError(
                "A running fetch cannot be interrupted safely; retry cancellation when it finishes"
            )
        canceled = 0
        for job in jobs:
            if job.status == JobStatus.QUEUED.value:
                job.status = JobStatus.CANCELED.value
                job.last_error = f"Canceled by administrator: {reason}"
                canceled += 1
        if not canceled:
            raise ConflictError("This data job has no queued work to cancel")
        root.payload = {**(root.payload or {}), "review_state": "canceled"}
        self._audit(
            "data_job:cancel",
            root.id,
            reason,
            None,
            {"canceled_job_count": canceled},
            entity_type="data_job",
        )
        self.session.commit()
        return self._data_job_summary(root, include_samples=True)

    def retry_data_job(self, job_id: str, *, reason: str) -> dict[str, Any]:
        root = self._data_job(job_id)
        children, _ = self._data_job_records(root)
        retryable = [
            job for job in [root, *children]
            if job.status in {JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value}
        ]
        if not retryable:
            raise ConflictError("This data job has no failed work to retry")
        for job in retryable:
            job.status = JobStatus.QUEUED.value
            job.attempts = 0
            job.run_after = utcnow()
            job.locked_at = None
            job.dead_lettered_at = None
            job.last_error = None
            job.completed_at = None
        root.payload = {**(root.payload or {}), "review_state": "pending"}
        self._audit(
            "data_job:retry",
            root.id,
            reason,
            None,
            {"retried_job_count": len(retryable)},
            entity_type="data_job",
        )
        self.session.commit()
        return self._data_job_summary(root, include_samples=True)

    def overview(self) -> dict[str, Any]:
        all_businesses = list(self.session.scalars(select(BusinessModel)))
        businesses = [business for business in all_businesses if business.status == "active"]
        states = self._validation_states(
            [business.id for business in businesses],
            include_quality=False,
        )
        status_counts = Counter(business.status for business in all_businesses)
        validation_counts = Counter(states[business.id]["state"] for business in businesses)
        trade_rows = list(
            self.session.execute(
                select(
                    NicheModel.slug,
                    NicheModel.label,
                    func.count(func.distinct(BusinessNicheMembershipModel.business_id)).label(
                        "business_count"
                    ),
                )
                .join(
                    BusinessNicheMembershipModel,
                    BusinessNicheMembershipModel.niche_id == NicheModel.id,
                )
                .join(
                    BusinessModel,
                    BusinessModel.id == BusinessNicheMembershipModel.business_id,
                )
                .where(
                    NicheModel.active.is_(True),
                    BusinessModel.status == "active",
                )
                .group_by(NicheModel.slug, NicheModel.label)
                .order_by(
                    func.count(func.distinct(BusinessNicheMembershipModel.business_id)).desc(),
                    NicheModel.label,
                )
            )
        )
        return {
            "total": len(businesses),
            "active": status_counts["active"],
            "quarantined": status_counts["quarantined"],
            "archived": status_counts["archived"],
            "fully_validated": validation_counts["passed"],
            "needs_attention": validation_counts["attention"],
            "incomplete": validation_counts["incomplete"],
            "searchable": self.session.scalar(
                select(func.count(func.distinct(BusinessModel.id)))
                .select_from(BusinessModel)
                .join(
                    BusinessNicheMembershipModel,
                    BusinessNicheMembershipModel.business_id == BusinessModel.id,
                )
                .where(active_membership_condition())
                .where(*searchable_business_conditions())
            ) or 0,
            "trade_groups": [
                {"slug": slug, "label": label, "count": business_count}
                for slug, label, business_count in trade_rows
            ],
            "match_attributes": [
                {
                    "key": definition.key,
                    "label": MATCH_ATTRIBUTE_LABELS.get(
                        definition.key,
                        f"Opportunity: {definition.label}",
                    ),
                    "category": definition.category,
                }
                for definition in self._match_attribute_definitions()
            ],
        }

    def list_businesses(
        self,
        *,
        query: str | None,
        validation: str | None,
        quality: str | None,
        sort: str,
        status: str | None,
        niche_slug: str | None,
        market_key: str | None,
        page: int,
        page_size: int,
        evaluation_state: str | None = None,
        eligibility_state: str | None = None,
        match_attribute: str | None = None,
        match_state: str | None = None,
    ) -> dict[str, Any]:
        statement = select(BusinessModel)
        membership_joined = False
        all_match_definitions = self._match_attribute_definitions()
        match_definition: SignalDefinitionModel | None = None
        if query:
            pattern = f"%{query.strip()}%"
            statement = statement.where(
                or_(
                    BusinessModel.display_name.ilike(pattern),
                    BusinessModel.address.ilike(pattern),
                    BusinessModel.domain.ilike(pattern),
                    BusinessModel.phone.ilike(pattern),
                )
            )
        if status:
            statement = statement.where(BusinessModel.status == status)
        if match_attribute:
            statement = statement.join(
                BusinessNicheMembershipModel,
                BusinessNicheMembershipModel.business_id == BusinessModel.id,
            ).join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
            membership_joined = True
            definitions = {
                definition.key: definition
                for definition in all_match_definitions
            }
            match_definition = definitions.get(match_attribute)
            if match_definition is None:
                raise ValidationError(
                    "Unknown audience-match attribute",
                    {"match_attribute": match_attribute},
                )
        if niche_slug or market_key:
            if not membership_joined:
                statement = statement.join(
                    BusinessNicheMembershipModel,
                    BusinessNicheMembershipModel.business_id == BusinessModel.id,
                ).join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
            if niche_slug:
                statement = statement.where(NicheModel.slug == niche_slug)
            if market_key:
                statement = statement.where(BusinessNicheMembershipModel.market_key == market_key)
        businesses = list(
            self.session.scalars(statement.distinct().order_by(BusinessModel.display_name))
        )
        business_ids = [business.id for business in businesses]
        memberships = self._primary_memberships(
            business_ids,
            niche_slug=niche_slug,
            market_key=market_key,
        )
        validation_scopes = {
            business_id: (membership.niche_id, membership.market_key)
            for business_id, (membership, _niche) in memberships.items()
        }
        states = self._validation_states(
            business_ids,
            validation_scopes=validation_scopes,
        )
        rows = [
            self._business_summary(
                business,
                states[business.id],
                memberships.get(business.id),
                match_definition=match_definition,
                match_definitions=all_match_definitions,
            )
            for business in businesses
        ]
        evaluation_state_counts = {
            state: 0
            for state in (
                "validated",
                "not_evaluated",
                "not_validated",
                "not_valid",
            )
        }
        evaluation_state_counts.update(
            Counter(row["evaluation_state"] for row in rows)
        )
        eligibility_state_counts = {
            state: 0 for state in ("target", "estimated", "excluded")
        }
        eligibility_state_counts.update(
            Counter(row["eligibility_state"] for row in rows)
        )
        if eligibility_state not in {None, "", "all"}:
            if eligibility_state not in eligibility_state_counts:
                raise ValidationError(
                    "Unknown business eligibility state",
                    {"eligibility_state": eligibility_state},
                )
            rows = [
                row for row in rows if row["eligibility_state"] == eligibility_state
            ]
        if evaluation_state not in {None, "", "all"}:
            if evaluation_state not in evaluation_state_counts:
                raise ValidationError(
                    "Unknown evaluation state",
                    {"evaluation_state": evaluation_state},
                )
            rows = [
                row for row in rows if row["evaluation_state"] == evaluation_state
            ]
        match_state_counts = {
            state: 0
            for state in (
                "matched",
                "not_evaluated",
                "not_validated",
                "does_not_match",
                "not_qualified",
            )
        }
        if match_definition is not None:
            match_state_counts.update(Counter(row["match_state"] for row in rows))
            selected_match_state = match_state or "matched"
            if selected_match_state != "all":
                if selected_match_state not in match_state_counts:
                    raise ValidationError(
                        "Unknown match state",
                        {"match_state": selected_match_state},
                    )
                rows = [
                    row for row in rows if row["match_state"] == selected_match_state
                ]
        elif match_state not in {None, "", "all"}:
            raise ValidationError(
                "Match state requires a selected match attribute",
                {"match_state": match_state},
            )
        if validation:
            rows = [row for row in rows if row["validation_state"] == validation]
        if quality == "reliable":
            rows = [row for row in rows if row["data_quality_score"] is not None and row["data_quality_score"] >= 85]
        elif quality == "review":
            rows = [row for row in rows if row["data_quality_score"] is not None and 65 <= row["data_quality_score"] < 85]
        elif quality == "poor":
            rows = [row for row in rows if row["data_quality_score"] is not None and row["data_quality_score"] < 65]
        elif quality == "refresh_required":
            rows = [row for row in rows if row["data_quality_label"] == "refresh_required"]
        elif quality == "missing_evidence":
            rows = [row for row in rows if row["data_quality_label"] == "missing_evidence"]
        elif quality == "pending":
            rows = [row for row in rows if row["data_quality_score"] is None]
        elif quality:
            raise ValidationError("Unknown data quality filter", {"quality": quality})
        if sort in {"candidate_asc", "lead_asc"}:
            rows.sort(
                key=lambda row: (
                    -_lead_sort_rank(row),
                    row["lead_assessment"]["priority_score"],
                    row["display_name"].lower(),
                )
            )
        elif sort in {"candidate_desc", "lead_desc"}:
            rows.sort(
                key=lambda row: (
                    _lead_sort_rank(row),
                    -row["lead_assessment"]["priority_score"],
                    row["display_name"].lower(),
                )
            )
        elif sort == "score_asc":
            rows.sort(key=lambda row: (row["data_quality_score"] is not None, row["data_quality_score"] or 0, row["display_name"].lower()))
        elif sort == "score_desc":
            rows.sort(key=lambda row: (row["data_quality_score"] is None, -(row["data_quality_score"] or 0), row["display_name"].lower()))
        elif sort == "name":
            rows.sort(key=lambda row: row["display_name"].lower())
        else:
            raise ValidationError("Unknown business sort", {"sort": sort})
        total = len(rows)
        start = (page - 1) * page_size
        return {
            "items": rows[start : start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
            "match_state_counts": match_state_counts,
            "evaluation_state_counts": evaluation_state_counts,
            "eligibility_state_counts": eligibility_state_counts,
        }

    def _match_attribute_definitions(self) -> list[SignalDefinitionModel]:
        rows = self.session.scalars(
            select(SignalDefinitionModel)
            .join(
                ServiceSignalMappingModel,
                ServiceSignalMappingModel.signal_definition_id == SignalDefinitionModel.id,
            )
            .join(
                ServiceDefinitionModel,
                ServiceDefinitionModel.id == ServiceSignalMappingModel.service_definition_id,
            )
            .where(
                ServiceDefinitionModel.status == "active",
                SignalDefinitionModel.status == "active",
                SignalDefinitionModel.opportunity_direction != "none",
            )
            .order_by(
                ServiceDefinitionModel.sort_order,
                ServiceSignalMappingModel.sort_order,
                SignalDefinitionModel.label,
            )
        ).unique()
        return list(rows)

    def detail(
        self,
        business_id: str,
        *,
        match_attribute: str | None = None,
        niche_slug: str | None = None,
        market_key: str | None = None,
    ) -> dict[str, Any]:
        business = self._business(business_id)
        memberships = list(
            self.session.execute(
                select(BusinessNicheMembershipModel, NicheModel)
                .join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
                .where(BusinessNicheMembershipModel.business_id == business_id)
                .order_by(BusinessNicheMembershipModel.confidence.desc())
            )
        )
        primary_membership = next(
            (
                membership
                for membership in memberships
                if (niche_slug is None or membership[1].slug == niche_slug)
                and (market_key is None or membership[0].market_key == market_key)
            ),
            memberships[0] if memberships else None,
        )
        validation_scopes = (
            {
                business_id: (
                    primary_membership[0].niche_id,
                    primary_membership[0].market_key,
                )
            }
            if primary_membership is not None
            else None
        )
        state = self._validation_states(
            [business_id],
            validation_scopes=validation_scopes,
        )[business_id]
        attributes = list(
            self.session.scalars(
                select(BusinessAttributeModel)
                .where(
                    BusinessAttributeModel.business_id == business_id,
                    BusinessAttributeModel.row_type == "attribute",
                )
                .order_by(BusinessAttributeModel.attribute_key)
            )
        )
        active_signals = SignalDefinitionRepository(self.session).list(status="active")
        attributes_by_definition = {
            attribute.signal_definition_id: attribute
            for attribute in attributes
            if attribute.signal_definition_id is not None
        }
        attributes_by_key = {
            attribute.attribute_key: attribute for attribute in attributes
        }
        sources = list(
            self.session.scalars(
                select(SourceItemModel)
                .where(SourceItemModel.business_id == business_id)
                .order_by(SourceItemModel.fetched_at.desc())
                .limit(30)
            )
        )
        contacts = list(
            self.session.scalars(
                select(ContactModel)
                .where(ContactModel.business_id == business_id)
                .order_by(ContactModel.last_seen_at.desc())
            )
        )
        audit = list(
            self.session.scalars(
                select(AdminAuditEventModel)
                .where(
                    AdminAuditEventModel.entity_type == "business",
                    AdminAuditEventModel.entity_id == business_id,
                )
                .order_by(AdminAuditEventModel.created_at.desc())
                .limit(50)
            )
        )
        all_match_definitions = self._match_attribute_definitions()
        match_definition = next(
            (
                definition
                for definition in all_match_definitions
                if definition.key == match_attribute
            ),
            None,
        )
        if match_attribute and match_definition is None:
            raise ValidationError(
                "Unknown audience-match attribute",
                {"match_attribute": match_attribute},
            )
        return {
            **self._business_summary(
                business,
                state,
                primary_membership,
                match_definition=match_definition,
                match_definitions=all_match_definitions,
            ),
            "normalized_name": business.normalized_name,
            "latitude": business.latitude,
            "longitude": business.longitude,
            "customer_kind": business.customer_kind,
            "is_chain": business.is_chain,
            "is_franchise": business.is_franchise,
            "is_directory": business.is_directory,
            "is_agency": business.is_agency,
            "memberships": [
                {
                    "id": membership.id,
                    "niche_slug": niche.slug,
                    "niche_label": niche.label,
                    "market_key": membership.market_key,
                    "confidence": membership.confidence,
                }
                for membership, niche in memberships
            ],
            "attributes": [
                {
                    "id": attribute.id,
                    "key": attribute.attribute_key,
                    "value": _attribute_value(attribute),
                    "confidence": attribute.confidence,
                    "resolution_state": attribute.resolution_state,
                    "evidence_state": attribute.resolution_state,
                    "observed_at": attribute.observed_at,
                    "expires_at": attribute.expires_at,
                }
                for attribute in attributes
            ],
            "signals": [
                _business_signal_dict(
                    definition,
                    attributes_by_definition.get(definition.id)
                    or attributes_by_key.get(definition.key),
                )
                for definition in active_signals
            ],
            "sources": [
                {
                    "id": item.id,
                    "provider": item.provider_id,
                    "state": item.state,
                    "source_url": item.source_url,
                    "title": item.title,
                    "fetched_at": item.fetched_at,
                    "last_error": item.last_error,
                }
                for item in sources
            ],
            "contacts": [
                {
                    "id": contact.id,
                    "name": contact.name,
                    "role": contact.role,
                    "email": contact.email,
                    "phone": contact.phone,
                    "verification_status": contact.verification_status,
                    "verification_provider": contact.verification_provider,
                    "verification_checked_at": contact.verification_checked_at,
                    "verification_reason": contact.verification_reason,
                    "verification_score": contact.verification_score,
                    "first_seen_at": contact.first_seen_at,
                    "last_seen_at": contact.last_seen_at,
                }
                for contact in contacts
            ],
            "audit": [
                {
                    "id": event.id,
                    "action": event.action,
                    "reason": event.reason,
                    "actor_email": event.actor_email,
                    "before": event.before,
                    "after": event.after,
                    "created_at": event.created_at,
                }
                for event in audit
            ],
            "delete_dependencies": {},
        }

    def attribute_lineage(self, business_id: str) -> dict[str, Any]:
        self._business(business_id)
        attributes = list(
            self.session.scalars(
                select(BusinessAttributeModel)
                .where(
                    BusinessAttributeModel.business_id == business_id,
                    BusinessAttributeModel.row_type == "attribute",
                )
                .order_by(BusinessAttributeModel.attribute_key)
            )
        )
        definition_ids = {
            attribute.signal_definition_id
            for attribute in attributes
            if attribute.signal_definition_id is not None
        }
        attribute_keys = {attribute.attribute_key for attribute in attributes}
        definitions = list(
            self.session.scalars(
                select(SignalDefinitionModel).where(
                    or_(
                        SignalDefinitionModel.id.in_(definition_ids),
                        SignalDefinitionModel.key.in_(
                            tuple(set(attribute_keys) | set(TRACKED_ATTRIBUTE_KEYS))
                        ),
                    )
                )
            )
        )
        definitions_by_id = {definition.id: definition for definition in definitions}
        definitions_by_key = {definition.key: definition for definition in definitions}

        evidence_ids = {
            evidence_id
            for attribute in attributes
            for evidence_id in (attribute.supporting_evidence_ids or [])
            if evidence_id is not None
        }
        evidence_records = list(
            self.session.scalars(
                select(BusinessAttributeModel)
                .where(
                    BusinessAttributeModel.business_id == business_id,
                    BusinessAttributeModel.id.in_(evidence_ids),
                    BusinessAttributeModel.row_type == "evidence",
                )
                .order_by(BusinessAttributeModel.observed_at.desc())
            )
        ) if evidence_ids else []

        catalog_definition_ids = {
            definition.id
            for definition in definitions
            if definition.key in TRACKED_ATTRIBUTE_KEYS
        }
        mapping_rows = list(
            self.session.execute(
                select(ServiceSignalMappingModel, ServiceDefinitionModel)
                .join(
                    ServiceDefinitionModel,
                    ServiceDefinitionModel.id
                    == ServiceSignalMappingModel.service_definition_id,
                )
                .where(
                    ServiceSignalMappingModel.signal_definition_id.in_(
                        definition_ids | catalog_definition_ids
                    )
                )
                .order_by(ServiceDefinitionModel.sort_order, ServiceDefinitionModel.label)
            )
        ) if definition_ids else []
        mappings_by_definition: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for mapping, service in mapping_rows:
            mappings_by_definition[mapping.signal_definition_id].append(
                {
                    "id": service.id,
                    "key": service.key,
                    "label": service.label,
                    "status": service.status,
                    "weight": mapping.weight,
                }
            )

        return {
            "business_id": business_id,
            "attribute_definitions": [
                {
                    "key": key,
                    "label": (
                        definitions_by_key[key].label
                        if key in definitions_by_key
                        else key.replace("_", " ").title()
                    ),
                    "category": ATTRIBUTE_GROUP_BY_KEY[key]["key"],
                    "category_label": ATTRIBUTE_GROUP_BY_KEY[key]["label"],
                    "category_sort_order": ATTRIBUTE_GROUP_BY_KEY[key]["sort_order"],
                    "sort_order": ATTRIBUTE_SORT_ORDER[key],
                    "value_type": (
                        definitions_by_key[key].value_type
                        if key in definitions_by_key
                        else "text"
                    ),
                    "status": (
                        definitions_by_key[key].status
                        if key in definitions_by_key
                        else "not_configured"
                    ),
                }
                for key in TRACKED_ATTRIBUTE_KEYS
            ],
            "attributes": [
                _attribute_lineage_dict(
                    attribute,
                    definitions_by_id.get(attribute.signal_definition_id or "")
                    or definitions_by_key.get(attribute.attribute_key),
                    mappings_by_definition,
                )
                for attribute in attributes
            ],
            "evidence_records": [
                {
                    "id": evidence.id,
                    "source": evidence.source,
                    "external_id": evidence.external_id,
                    "query_signature": evidence.query_signature,
                    "content_hash": evidence.content_hash,
                    "source_url": evidence.source_url,
                    "payload": evidence.raw_payload,
                    "observed_at": evidence.observed_at,
                }
                for evidence in evidence_records
            ],
        }

    def business_json(self, business_id: str) -> dict[str, Any]:
        detail = self.detail(business_id)
        lineage = self.attribute_lineage(business_id)
        attributes_by_key = {
            attribute["key"]: attribute for attribute in lineage["attributes"]
        }
        evidence_by_id = {
            evidence["id"]: evidence for evidence in lineage["evidence_records"]
        }
        fallback_values = {
            "business_name": detail["display_name"],
            "trade_category": detail.get("niche_label") or detail.get("niche_slug"),
            "address": detail.get("address"),
            "phone": detail.get("phone"),
            "website_url": detail.get("website_url"),
            "domain": detail.get("domain"),
            "latitude": detail.get("latitude"),
            "longitude": detail.get("longitude"),
            "is_directory": detail.get("is_directory"),
            "is_chain": detail.get("is_chain"),
            "is_franchise": detail.get("is_franchise"),
        }
        attributes: dict[str, dict[str, Any]] = {}
        for definition in lineage["attribute_definitions"]:
            key = definition["key"]
            attribute = attributes_by_key.get(key)
            evidence = (
                evidence_by_id.get(attribute.get("source_evidence_id"))
                if attribute and attribute.get("source_evidence_id")
                else None
            )
            value = (
                attribute.get("value")
                if attribute is not None
                else fallback_values.get(key)
            )
            attributes[key] = {
                "label": definition["label"],
                "category": definition["category"],
                "observed": value is not None and value != "",
                "value": value,
                "opportunity_score": attribute.get("opportunity_score") if attribute else None,
                "score_reason": attribute.get("score_reason") if attribute else None,
                "evidence_confidence": attribute.get("evidence_confidence") if attribute else None,
                "resolution_state": attribute.get("resolution_state") if attribute else None,
                "evidence_state": attribute.get("evidence_state") if attribute else None,
                "observed_at": attribute.get("observed_at") if attribute else None,
                "expires_at": attribute.get("expires_at") if attribute else None,
                "source": (
                    {
                        "evidence_id": evidence["id"],
                        "provider": evidence["source"],
                        "url": evidence.get("source_url"),
                    }
                    if evidence is not None
                    else None
                ),
            }
        return {
            "business": {
                "id": detail["id"],
                "name": detail["display_name"],
                "state": detail["status"],
                "trade": detail.get("niche_label"),
                "market": detail.get("market_key"),
                "address": detail.get("address"),
                "coordinates": {
                    "latitude": detail.get("latitude"),
                    "longitude": detail.get("longitude"),
                },
                "website_url": detail.get("website_url"),
                "domain": detail.get("domain"),
                "phone": detail.get("phone"),
                "first_seen_at": detail.get("first_seen_at"),
                "last_seen_at": detail.get("last_seen_at"),
            },
            "lead_assessment": detail["lead_assessment"],
            "attributes": attributes,
            "contacts": detail.get("contacts", []),
            "evidence": {"records": lineage["evidence_records"]},
        }

    def export_businesses_json(self, business_ids: list[str]) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(business_ids))
        if len(unique_ids) > 500:
            raise ValidationError(
                "Too many businesses selected",
                {"maximum": 500, "selected": len(unique_ids)},
            )
        return {
            "exported_at": utcnow(),
            "business_count": len(unique_ids),
            "businesses": [self.business_json(business_id) for business_id in unique_ids],
        }

    def create(self, data: AdminBusinessCreate) -> dict[str, Any]:
        segment = self.session.scalar(
            select(BusinessIndexSegmentModel)
            .join(NicheModel, NicheModel.id == BusinessIndexSegmentModel.niche_id)
            .where(NicheModel.slug == data.niche_slug, BusinessIndexSegmentModel.market_key == data.market_key)
            .limit(1)
        )
        if segment is None:
            raise ValidationError("No business index segment exists for this niche and market")
        normalized_name = normalize_business_name(data.display_name)
        domain = normalize_domain(data.website_url)
        duplicate = self.session.scalar(
            select(BusinessModel).where(
                BusinessModel.normalized_name == normalized_name,
                BusinessModel.market_key == data.market_key,
            ).limit(1)
        )
        if duplicate is not None:
            raise ConflictError("A matching canonical business already exists", {"business_id": duplicate.id})
        now = utcnow()
        business = BusinessModel(
            id=new_id("business"),
            display_name=data.display_name.strip(),
            normalized_name=normalized_name,
            website_url=normalize_url(data.website_url),
            domain=domain,
            phone=normalize_phone(data.phone),
            address=data.address,
            geography=data.geography,
            category_key=data.niche_slug,
            market_key=data.market_key,
            latitude=data.latitude,
            longitude=data.longitude,
            customer_kind="unknown",
            status="quarantined",
            first_seen_at=now,
            last_seen_at=now,
        )
        self.session.add(business)
        self.session.flush()
        self.session.add(
            BusinessNicheMembershipModel(
                id=new_id("membership"),
                business_id=business.id,
                niche_id=segment.niche_id,
                market_key=data.market_key,
                confidence=1.0,
                evidence=[{"source": "admin", "source_url": data.source_url}],
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        source_value = SourceItemCreate(
            segment_id=segment.id,
            provider_id=data.source_provider,
            query=f"admin add {data.display_name}",
            source_url=normalize_url(data.source_url),
            title=data.display_name,
            raw_payload={
                "title": data.display_name,
                "url": normalize_url(data.source_url),
                "address": data.address,
                "geography": data.geography,
                "phone": data.phone,
                "website_url": normalize_url(data.website_url),
                "source": data.source_provider,
            },
            fetched_at=now,
        )
        source = SourceItemModel(
            id=new_id("source_item"),
            **source_value.model_dump(),
            content_hash=source_item_content_hash(source_value),
            state="validating",
            business_id=business.id,
        )
        self.session.add(source)
        self.session.flush()
        source.state = "validated"
        self._audit("create", business.id, data.reason, None, _business_dict(business))
        self.session.commit()
        return self.detail(business.id)

    def update(self, business_id: str, data: AdminBusinessUpdate) -> dict[str, Any]:
        business = self._business(business_id)
        before = _business_dict(business)
        updates = data.model_dump(exclude={"reason"}, exclude_unset=True)
        for field, value in updates.items():
            if field == "website_url":
                value = normalize_url(value)
                business.domain = normalize_domain(value)
            elif field == "phone":
                value = normalize_phone(value)
            elif field == "display_name" and value:
                value = value.strip()
                business.normalized_name = normalize_business_name(value)
            setattr(business, field, value)
        business.last_seen_at = utcnow()
        business.status = "quarantined"
        self._audit("update", business.id, data.reason, before, _business_dict(business))
        self.session.commit()
        return self.detail(business.id)

    def change_status(self, business_id: str, status: str, reason: str) -> dict[str, Any]:
        business = self._business(business_id)
        before = _business_dict(business)
        business.status = status
        self._audit(f"status:{status}", business.id, reason, before, _business_dict(business))
        self.session.commit()
        return self.detail(business.id)

    def revalidate(self, business_id: str, reason: str) -> dict[str, Any]:
        business = self._business(business_id)
        originals = list(
            self.session.scalars(select(SourceItemModel).where(SourceItemModel.business_id == business_id))
        )
        if not originals:
            raise ValidationError("This business has no source item to validate")
        original = min(
            originals,
            key=lambda item: (SOURCE_PRIORITY.get(item.provider_id, 99), -item.fetched_at.timestamp()),
        )
        segment = self.session.get(BusinessIndexSegmentModel, original.segment_id)
        if segment is None:
            raise ValidationError("The source item has no active segment")
        now = utcnow()
        source_value = SourceItemCreate(
            segment_id=original.segment_id,
            provider_id=original.provider_id,
            external_id=original.external_id,
            query=original.query,
            source_url=original.source_url,
            title=original.title,
            raw_payload=original.raw_payload,
            fetched_at=now,
        )
        source = SourceItemModel(
            id=new_id("source_item"),
            **source_value.model_dump(),
            content_hash=source_item_content_hash(source_value),
            state="validating",
            business_id=business_id,
        )
        self.session.add(source)
        self.session.flush()
        source.state = "validated"
        self._audit(
            "revalidate",
            business.id,
            reason,
            None,
            {"source_item_id": source.id, "status": source.state},
        )
        self.session.commit()
        return self.detail(business.id)

    def delete_dependencies(self, business_id: str) -> dict[str, int]:
        self._business(business_id)
        targets = self._dependent_record_ids(business_id)
        return {
            table_name: len(record_ids)
            for table_name, record_ids in targets.items()
            if table_name != "businesses" and record_ids
        }

    def _dependent_record_ids(self, business_id: str) -> dict[str, set[Any]]:
        targets: dict[str, set[Any]] = {"businesses": {business_id}}
        for table in Base.metadata.sorted_tables:
            if table.name in {"businesses", "admin_audit_events"}:
                continue
            primary_keys = list(table.primary_key.columns)
            if len(primary_keys) != 1:
                continue
            conditions = []
            for column in table.columns:
                for foreign_key in column.foreign_keys:
                    parent_ids = targets.get(foreign_key.column.table.name)
                    if parent_ids:
                        conditions.append(column.in_(parent_ids))
            if not conditions:
                continue
            record_ids = set(
                self.session.scalars(
                    select(primary_keys[0]).select_from(table).where(or_(*conditions))
                )
            )
            if record_ids:
                targets[table.name] = record_ids
        return targets

    def delete(self, business_id: str, confirmation: str, reason: str) -> None:
        business = self._business(business_id)
        if confirmation.strip() != business.display_name:
            raise ValidationError("Confirmation must exactly match the business name")
        self._purge_business(business, reason)
        self.session.commit()

    def bulk_delete(
        self,
        business_ids: list[str],
        confirmation: str,
        reason: str,
    ) -> dict[str, int]:
        unique_ids = list(dict.fromkeys(business_ids))
        expected = f"DELETE {len(unique_ids)} BUSINESSES"
        if confirmation.strip() != expected:
            raise ValidationError(f'Confirmation must exactly match "{expected}"')
        businesses = [self._business(business_id) for business_id in unique_ids]
        for business in businesses:
            self._purge_business(business, reason)
        self.session.commit()
        return {"deleted_businesses": len(businesses)}

    def _purge_business(self, business: BusinessModel, reason: str) -> None:
        business_id = business.id
        targets = self._dependent_record_ids(business_id)
        dependencies = {
            table_name: len(record_ids)
            for table_name, record_ids in targets.items()
            if table_name != "businesses" and record_ids
        }
        before = _business_dict(business)

        # This is an explicitly confirmed administrative purge. Delete dependent
        # rows in reverse FK order so a false business entity does not leave facts,
        # observations, memberships, or workflow state behind.
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in {"businesses", "admin_audit_events"}:
                continue
            record_ids = targets.get(table.name)
            primary_keys = list(table.primary_key.columns)
            if record_ids and len(primary_keys) == 1:
                self.session.execute(
                    sql_delete(table).where(primary_keys[0].in_(record_ids))
                )

        self._audit(
            "delete",
            business.id,
            reason,
            before,
            {"deleted_dependencies": dependencies},
        )
        self.session.delete(business)

    def _business(self, business_id: str) -> BusinessModel:
        business = self.session.get(BusinessModel, business_id)
        if business is None:
            raise NotFoundError("business not found", {"business_id": business_id})
        return business

    def _signal_definition(self, signal_id: str) -> SignalDefinitionModel:
        definition = SignalDefinitionRepository(self.session).get(signal_id)
        if definition is None:
            raise NotFoundError("signal definition not found", {"signal_id": signal_id})
        return definition

    def _validate_signal_definition(self, definition: SignalDefinitionModel) -> None:
        config = definition.config or {}
        if definition.extractor_key == "payload_path" and not str(
            config.get("payload_path") or ""
        ).strip():
            raise ValidationError(
                "Payload-path extractors require config.payload_path",
                {"signal_id": definition.id},
            )
        if definition.opportunity_direction in {
            "lower_is_opportunity",
            "higher_is_opportunity",
        } and (
            not isinstance(config.get("opportunity_threshold"), (int, float))
            or isinstance(config.get("opportunity_threshold"), bool)
        ):
            raise ValidationError(
                "Numeric opportunity rules require config.opportunity_threshold",
                {"signal_id": definition.id},
            )
        values = config.get("opportunity_values")
        if definition.opportunity_direction == "missing_is_opportunity" and values is not None:
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                raise ValidationError(
                    "Text opportunity rules require a list of opportunity values",
                    {"signal_id": definition.id},
                )

    def _enqueue_signal_collection(
        self,
        definition: SignalDefinitionModel,
        *,
        reason: str,
        scope: str,
        business_ids: list[str],
        niche_slug: str | None,
        market_key: str | None,
        batch_size: int,
    ) -> list[dict[str, Any]]:
        # Website collection can inspect several pages per business. Keep each
        # bulk unit small enough to yield the worker to interactive requests.
        batch_size = min(batch_size, 10)
        target_ids = self._signal_collection_business_ids(
            scope=scope,
            business_ids=business_ids,
            niche_slug=niche_slug,
            market_key=market_key,
        )
        queue = QueueService(self.session)
        jobs = []
        for index in range(0, len(target_ids), batch_size):
            batch = target_ids[index:index + batch_size]
            job = queue.enqueue_signal_collection(
                signal_definition_id=definition.id,
                signal_version=definition.version,
                business_ids=batch,
                requested_by=self.auth.user_id,
                reason=reason,
                batch_number=(index // batch_size) + 1,
                commit=False,
            )
            jobs.append(
                {
                    "id": job.id,
                    "status": job.status,
                    "business_count": len(batch),
                    "batch_number": (index // batch_size) + 1,
                }
            )
        return jobs

    def _signal_collection_business_ids(
        self,
        *,
        scope: str,
        business_ids: list[str],
        niche_slug: str | None,
        market_key: str | None,
    ) -> list[str]:
        statement = select(BusinessModel.id).where(BusinessModel.status != "archived")
        if scope == "selected":
            if not business_ids:
                raise ValidationError("Selected scope requires at least one business")
            statement = statement.where(BusinessModel.id.in_(business_ids))
        elif scope == "segment":
            if not niche_slug or not market_key:
                raise ValidationError("Segment scope requires niche_slug and market_key")
            statement = (
                statement.join(
                    BusinessNicheMembershipModel,
                    BusinessNicheMembershipModel.business_id == BusinessModel.id,
                )
                .join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
                .where(
                    NicheModel.slug == niche_slug,
                    BusinessNicheMembershipModel.market_key == market_key,
                )
            )
        elif scope != "all":
            raise ValidationError("Unknown signal collection scope", {"scope": scope})
        found = list(self.session.scalars(statement.distinct().order_by(BusinessModel.id)))
        if scope == "selected":
            missing = set(business_ids) - set(found)
            if missing:
                raise NotFoundError("One or more businesses were not found", {"business_ids": sorted(missing)})
        return found

    def _data_job(self, job_id: str) -> QueueJobModel:
        job = self.session.get(QueueJobModel, job_id)
        if (
            job is None
            or job.type != JobType.BUSINESS_INDEX_REFRESH.value
            or not (job.payload or {}).get("admin_requested")
        ):
            raise NotFoundError("admin data job not found", {"job_id": job_id})
        return job

    def _data_job_records(
        self,
        root: QueueJobModel,
    ) -> tuple[list[QueueJobModel], list[SourceItemModel]]:
        children = list(
            self.session.scalars(
                select(QueueJobModel)
                .where(
                    QueueJobModel.parent_run_id == root.id,
                    QueueJobModel.type == JobType.SOURCE_FETCH.value,
                )
                .order_by(QueueJobModel.created_at)
            )
        )
        child_ids = [job.id for job in children]
        items = [] if not child_ids else list(
            self.session.scalars(
                select(SourceItemModel)
                .where(SourceItemModel.job_id.in_(child_ids))
                .order_by(SourceItemModel.fetched_at.desc(), SourceItemModel.id)
            )
        )
        return children, items

    def _data_job_summary(
        self,
        root: QueueJobModel,
        *,
        include_samples: bool = False,
    ) -> dict[str, Any]:
        segment = self.session.get(
            BusinessIndexSegmentModel,
            str((root.payload or {}).get("segment_id")),
        )
        children, items = self._data_job_records(root)
        state_counts = Counter(item.state for item in items)
        source_counts = Counter(item.provider_id for item in items)
        child_statuses = Counter(job.status for job in children)
        pending_states = {SourceItemState.FETCHED.value, SourceItemState.RELEVANT.value}
        processing_states = {
            SourceItemState.RESOLUTION_QUEUED.value,
            SourceItemState.AUDIT_PENDING.value,
        }
        validated_states = {
            SourceItemState.AUDITED.value,
            SourceItemState.ELIGIBLE.value,
        }
        review_state = str((root.payload or {}).get("review_state", "pending"))
        status = self._data_job_status(
            root,
            child_statuses=child_statuses,
            state_counts=state_counts,
            review_state=review_state,
        )
        raw_completeness = {
            "with_title": sum(bool(item.title) for item in items),
            "with_source_url": sum(bool(item.source_url) for item in items),
            "with_external_id": sum(bool(item.external_id) for item in items),
            "with_address": sum(
                _payload_has(item.raw_payload, {"address", "formatted_address"})
                for item in items
            ),
            "with_phone": sum(
                _payload_has(item.raw_payload, {"phone", "phone_number", "telephone"})
                for item in items
            ),
            "with_website": sum(
                _payload_has(item.raw_payload, {"website", "website_url", "domain"})
                for item in items
            ),
        }
        result = {
            "id": root.id,
            "segment_id": segment.id if segment else (root.payload or {}).get("segment_id"),
            "segment_label": (
                f"{segment.niche.label} · {segment.market_label}" if segment else "Unknown segment"
            ),
            "processing_mode": (root.payload or {}).get("processing_mode", "automatic"),
            "status": status,
            "review_state": review_state,
            "reason": (root.payload or {}).get("reason"),
            "created_at": root.created_at,
            "updated_at": root.updated_at,
            "completed_at": root.completed_at,
            "source_job_counts": dict(child_statuses),
            "source_counts": dict(source_counts),
            "state_counts": dict(state_counts),
            "total_items": len(items),
            "pending_review": sum(state_counts[state] for state in pending_states),
            "processing": sum(state_counts[state] for state in processing_states),
            "validated": sum(state_counts[state] for state in validated_states),
            "needs_attention": sum(
                state_counts[state]
                for state in {
                    SourceItemState.NEEDS_REVIEW.value,
                    SourceItemState.REJECTED.value,
                    SourceItemState.EXCLUDED.value,
                    SourceItemState.FAILED.value,
                }
            ),
            "businesses_created": len({item.business_id for item in items if item.business_id}),
            "completeness": raw_completeness,
            "errors": [job.last_error for job in [root, *children] if job.last_error],
        }
        if include_samples:
            result["source_items"] = [
                {
                    "id": item.id,
                    "provider": item.provider_id,
                    "state": item.state,
                    "title": item.title,
                    "source_url": item.source_url,
                    "external_id": item.external_id,
                    "business_id": item.business_id,
                    "fetched_at": item.fetched_at,
                    "address": _payload_value(item.raw_payload, {"address", "formatted_address"}),
                    "phone": _payload_value(
                        item.raw_payload,
                        {"phone", "phone_number", "telephone"},
                    ),
                    "website": _payload_value(
                        item.raw_payload,
                        {"website", "website_url", "domain"},
                    ),
                }
                for item in items[:200]
            ]
            result["source_items_truncated"] = len(items) > 200
        return result

    def _data_job_status(
        self,
        root: QueueJobModel,
        *,
        child_statuses: Counter,
        state_counts: Counter,
        review_state: str,
    ) -> str:
        if review_state in {"discarded", "canceled"}:
            return review_state
        if root.status == JobStatus.CANCELED.value:
            return "canceled"
        if root.status in {JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value}:
            return "failed"
        if root.status in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}:
            return "queued" if root.status == JobStatus.QUEUED.value else "collecting"
        if child_statuses[JobStatus.QUEUED.value] or child_statuses[JobStatus.RUNNING.value]:
            return "collecting"
        if child_statuses[JobStatus.FAILED.value] or child_statuses[JobStatus.DEAD_LETTER.value]:
            return "failed"
        if (root.payload or {}).get("processing_mode") == "review_first":
            pending = (
                state_counts[SourceItemState.FETCHED.value]
                + state_counts[SourceItemState.RELEVANT.value]
            )
            processing = sum(
                state_counts[state]
                for state in {
                    SourceItemState.RESOLUTION_QUEUED.value,
                    SourceItemState.AUDIT_PENDING.value,
                }
            )
            if review_state == "sample_processing":
                return "validating_sample" if processing else "sample_ready"
            if pending and review_state != "approved":
                return "awaiting_review"
        if any(
            state_counts[state]
            for state in {
                SourceItemState.FETCHED.value,
                SourceItemState.RELEVANT.value,
                SourceItemState.RESOLUTION_QUEUED.value,
                SourceItemState.AUDIT_PENDING.value,
            }
        ):
            return "validating"
        return "completed"

    def _validation_states(
        self,
        business_ids: list[str],
        *,
        include_quality: bool = True,
        validation_scopes: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        fact_attributes = self._fact_attribute_scores(business_ids) if include_quality else {}
        businesses_with_attributes: set[str] = set(fact_attributes)
        if business_ids and not include_quality:
            businesses_with_attributes = set(
                self.session.scalars(
                    select(BusinessAttributeModel.business_id)
                    .where(
                        BusinessAttributeModel.business_id.in_(business_ids),
                        BusinessAttributeModel.row_type == "attribute",
                    )
                    .distinct()
                )
            )
        result: dict[str, dict[str, Any]] = {}
        for business_id in business_ids:
            attributes = fact_attributes.get(business_id, [])
            has_attributes = business_id in businesses_with_attributes
            state = "passed" if has_attributes else "incomplete"
            result[business_id] = {
                "state": state,
                "evaluation_state": "evaluated" if has_attributes else "not_evaluated",
                "_fact_attributes": attributes,
            }
        return result

    def _fact_attribute_scores(self, business_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not business_ids:
            return {}
        now = utcnow()
        facts = list(
            self.session.scalars(
                select(BusinessAttributeModel)
                .where(
                    BusinessAttributeModel.business_id.in_(business_ids),
                    BusinessAttributeModel.row_type == "attribute",
                )
                .order_by(
                    BusinessAttributeModel.business_id,
                    BusinessAttributeModel.attribute_key,
                    BusinessAttributeModel.observed_at.desc(),
                )
            )
        )
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)
        seen: set[tuple[str, str]] = set()
        for fact in facts:
            identity = (fact.business_id, fact.attribute_key)
            if identity in seen:
                continue
            seen.add(identity)
            result[fact.business_id].append(_fact_attribute_component(fact, now=now))
        return dict(result)

    def _business_summary(
        self,
        business: BusinessModel,
        state: dict[str, Any],
        membership=None,
        *,
        match_definition: SignalDefinitionModel | None = None,
        match_definitions: list[SignalDefinitionModel] | None = None,
    ) -> dict[str, Any]:
        quality = _attribute_data_quality_score(
            state.get("_fact_attributes", []),
        )
        assessment = _admin_lead_assessment(
            business,
            state.get("_fact_attributes", []),
            match_definition,
            match_definitions or [],
        )
        match_state = _admin_match_state(
            assessment,
            match_definition,
        )
        return {
            "id": business.id,
            "display_name": business.display_name,
            "status": business.status,
            "validation_state": state["state"],
            "evaluation_state": state["evaluation_state"],
            **quality,
            "match_state": match_state,
            "lead_assessment": assessment,
            "lead_priority_score": assessment["priority_score"],
            "lead_priority_label": assessment["priority_label"],
            "eligibility_state": assessment["eligibility"]["state"],
            "evidence_coverage_state": assessment["evidence_coverage"]["state"],
            "verified_opportunity_count": assessment["verified_opportunity_count"],
            "website_url": business.website_url,
            "domain": business.domain,
            "phone": business.phone,
            "address": business.address,
            "geography": business.geography,
            "market_key": membership[0].market_key if membership else business.market_key,
            "niche_slug": membership[1].slug if membership else business.category_key,
            "niche_label": membership[1].label if membership else business.category_key,
            "first_seen_at": business.first_seen_at,
            "last_seen_at": business.last_seen_at,
        }

    def _primary_memberships(
        self,
        business_ids: list[str],
        *,
        niche_slug: str | None = None,
        market_key: str | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if not business_ids:
            return result
        statement = (
            select(BusinessNicheMembershipModel, NicheModel)
            .join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
            .where(BusinessNicheMembershipModel.business_id.in_(business_ids))
            .order_by(BusinessNicheMembershipModel.confidence.desc())
        )
        if niche_slug:
            statement = statement.where(NicheModel.slug == niche_slug)
        if market_key:
            statement = statement.where(
                BusinessNicheMembershipModel.market_key == market_key
            )
        rows = self.session.execute(statement)
        for membership, niche in rows:
            result.setdefault(membership.business_id, (membership, niche))
        return result

    def _audit(
        self,
        action: str,
        entity_id: str,
        reason: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        *,
        entity_type: str = "business",
    ) -> None:
        self.session.add(
            AdminAuditEventModel(
                id=new_id("admin_audit"),
                actor_id=self.auth.user_id,
                actor_email=self.auth.email,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                reason=reason,
                before=before,
                after=after,
            )
        )


def _lead_sort_rank(row: dict[str, Any]) -> int:
    return {
        "candidate": 0,
        "healthy": 1,
        "excluded": 2,
    }.get(row["lead_assessment"]["lead_state"], 5)


def _admin_match_state(
    assessment: dict[str, Any],
    match_definition: SignalDefinitionModel | None,
) -> str:
    if match_definition is None:
        return "not_scoped"
    eligibility = assessment["eligibility"]["state"]
    if eligibility == "excluded":
        return "not_qualified"
    if eligibility == "estimated":
        return "not_validated"
    opportunity = assessment.get("selected_opportunity")
    if opportunity is None or opportunity["state"] == "review":
        return "not_evaluated"
    if opportunity["state"] == "gap":
        return "matched"
    return "does_not_match"


def _admin_lead_assessment(
    business: BusinessModel,
    fact_attributes: list[dict[str, Any]],
    match_definition: SignalDefinitionModel | None,
    match_definitions: list[SignalDefinitionModel],
) -> dict[str, Any]:
    """Return explicit decisions without combining them into one score."""

    facts = {item["key"]: item for item in fact_attributes}
    identity_ok = bool(business.display_name and not business.is_directory)
    trade_ok = bool(business.category_key)
    location_ok = bool(
        business.market_key
        or business.address
        or (business.latitude is not None and business.longitude is not None)
    )
    identity_check = {
        "key": "identity", "label": "Business identity",
        "state": "passed" if identity_ok else "failed", "required": True,
        "reason": "Business record has a usable identity." if identity_ok else "Business identity is missing or is a directory.",
    }
    trade_check = {
        "key": "trade", "label": "Trade/category",
        "state": "passed" if trade_ok else "failed", "required": True,
        "reason": "Trade/category is present." if trade_ok else "Trade/category is missing.",
    }
    location_check = {
        "key": "location", "label": "Market coverage",
        "state": "passed" if location_ok else "unknown", "required": False,
        "reason": "Market or location evidence is present." if location_ok else "Location is not stored.",
    }
    operational = facts.get("business_operational")
    operational_usable = bool(
        operational and operational.get("evidence_state") == "usable"
    )
    operational_value = operational.get("value") if operational else None
    operational_check = {
        "key": "business_operational",
        "label": "Operational status",
        "state": (
            "failed"
            if operational_usable and operational_value is False
            else "passed"
            if operational_usable and operational_value is True
            else "unknown"
        ),
        "required": False,
        "reason": (
            "Business is confirmed closed."
            if operational_usable and operational_value is False
            else "Business is confirmed operational."
            if operational_usable and operational_value is True
            else "Operational status is unknown; no closure was reported."
        ),
    }
    checks = [identity_check, trade_check, location_check, operational_check]
    excluded_reasons = []
    if business.status != "active":
        excluded_reasons.append(f"Business record is {business.status}.")
    excluded_reasons.extend(
        check["reason"]
        for check in checks
        if check["state"] == "failed"
    )
    review_reasons = [
        check["reason"]
        for check in checks
        if check.get("required", True) and check["state"] == "unknown"
    ]
    eligibility_state = (
        "excluded"
        if excluded_reasons
        else "estimated"
        if review_reasons
        else "target"
    )

    definitions = (
        [match_definition]
        if match_definition is not None
        else list(match_definitions)
    )
    opportunities = [
        _opportunity_assessment(definition, facts.get(definition.key))
        for definition in definitions
    ]
    opportunity_groups = _opportunity_groups(opportunities)
    selected_opportunity = opportunities[0] if match_definition is not None else None
    verified = [item for item in opportunities if item["state"] == "gap"]
    evaluated_count = sum(
        item["state"] != "review" for item in opportunities
    )
    required_count = len(opportunities)
    coverage_state = (
        "missing"
        if evaluated_count == 0
        else "complete"
        if evaluated_count == required_count
        else "partial"
    )
    considered_opportunities = (
        [selected_opportunity] if selected_opportunity is not None else opportunities
    )
    priority = _website_lead_priority(
        eligibility_state=eligibility_state,
        eligibility_reasons=excluded_reasons or review_reasons,
        facts=facts,
        opportunities=considered_opportunities,
        has_website_url=bool(business.website_url),
    )
    return {
        "lead_state": priority["state"],
        "priority_score": priority["score"],
        "priority_label": priority["label"],
        "priority_confidence": priority["confidence"],
        "priority_reason": priority["reason"],
        "eligibility": {
            "state": eligibility_state,
            "checks": checks,
            "reasons": excluded_reasons or review_reasons,
        },
        "opportunities": opportunities,
        "opportunity_groups": opportunity_groups,
        "selected_opportunity": selected_opportunity,
        "verified_opportunity_count": len(verified),
        "evidence_coverage": {
            "state": coverage_state,
            "evaluated": evaluated_count,
            "required": required_count,
            "missing": [
                item["key"]
                for item in opportunities
                if item["state"] == "review"
            ],
        },
    }


def _opportunity_assessment(
    definition: SignalDefinitionModel,
    fact: dict[str, Any] | None,
) -> dict[str, Any]:
    label = MATCH_ATTRIBUTE_LABELS.get(definition.key, definition.label)
    if (
        fact is None
        or fact.get("evidence_state") != "usable"
        or fact.get("score") is None
    ):
        return {
            "key": definition.key,
            "label": label,
            "state": "review",
            "reason": "Website evidence is incomplete; priority is estimated.",
            "value": fact.get("value") if fact else None,
            "score": fact.get("score") if fact else None,
            "evidence_confidence": fact.get("evidence_confidence") if fact else None,
            "observed_at": fact.get("observed_at") if fact else None,
        }
    config = audience_match_config(
        definition.key,
        definition.opportunity_direction,
        definition.config,
    )
    minimum_score = float(config.get("audience_min_score", 50.001))
    matched = float(fact["score"]) >= minimum_score
    if definition.key == "website_status":
        matched = matched and fact.get("value") == "missing"
    return {
        "key": definition.key,
        "label": label,
        "state": "gap" if matched else "healthy",
        "reason": fact.get("basis") or fact.get("score_reason") or (
            "Verified website gap." if matched else "Measured website check is healthy."
        ),
        "value": fact.get("value"),
        "score": round(float(fact["score"]), 1),
        "evidence_confidence": fact.get("evidence_confidence"),
        "source_evidence_id": fact.get("source_evidence_id"),
        "observed_at": fact.get("observed_at"),
    }


def _website_lead_priority(
    *,
    eligibility_state: str,
    eligibility_reasons: list[str],
    facts: dict[str, dict[str, Any]],
    opportunities: list[dict[str, Any] | None],
    has_website_url: bool,
) -> dict[str, Any]:
    """Prioritize verified, measured, and estimated website potential.

    Incomplete evidence receives a confidence-adjusted estimate rather than a
    dead-end review state. The estimate affects ranking but never rewrites an
    unknown fact as a verified website defect.
    """

    considered = [item for item in opportunities if item is not None]
    operational = facts.get("business_operational")
    operational_active = bool(
        operational
        and operational.get("evidence_state") == "usable"
        and operational.get("value") is True
    )
    google_profile = facts.get("google_business_profile_present")
    google_profile_active = bool(
        google_profile
        and google_profile.get("evidence_state") == "usable"
        and google_profile.get("value") is True
    )
    website_status = facts.get("website_status")
    status_value = str(website_status.get("value") or "").strip().lower() if website_status else ""
    website_ownership = facts.get("website_ownership")
    ownership_verified = bool(
        website_ownership
        and website_ownership.get("evidence_state") == "usable"
        and str(website_ownership.get("value") or "").strip().lower() == "passed"
    )
    eligibility_factor = (
        1.0 if eligibility_state == "target" else ESTIMATED_ELIGIBILITY_FACTOR
    )

    def estimated_priority(
        base_score: float,
        *,
        label: str,
        reason: str,
    ) -> dict[str, Any]:
        score = round(base_score * eligibility_factor, 1)
        eligibility_note = (
            " " + " ".join(eligibility_reasons)
            if eligibility_reasons
            else ""
        )
        return {
            "state": "candidate",
            "score": score,
            "label": label,
            "confidence": "estimated",
            "reason": f"{reason}{eligibility_note}".strip(),
        }

    gaps = [item for item in considered if item["state"] == "gap"]
    missing_gap = next(
        (item for item in gaps if item["key"] == "website_status"),
        None,
    )
    if missing_gap is not None and operational_active:
        source = "active Google Business Profile" if google_profile_active else "active business evidence"
        if eligibility_state != "target":
            return estimated_priority(
                100.0,
                label="Website missing",
                reason=f"No owned website was found for a business supported by {source}.",
            )
        return {
            "state": "candidate",
            "score": 100.0,
            "label": "Website missing",
            "confidence": "verified",
            "reason": f"No owned website was found for a business supported by {source}.",
        }

    if status_value == "not_listed" and operational_active and google_profile_active:
        return estimated_priority(
            95.0,
            label="No website listed",
            reason="The active Google Business Profile lists no website.",
        )

    if has_website_url and status_value in {"present", "available"} and not ownership_verified:
        return estimated_priority(
            80.0,
            label="Estimated website potential",
            reason=(
                "The attached website has not been verified as belonging to this business; "
                "its quality result is not trusted yet."
            ),
        )

    if gaps:
        strongest = max(gaps, key=lambda item: float(item.get("score") or 0.0))
        score = round(float(strongest.get("score") or ESTIMATED_WEBSITE_UPGRADE_SCORE), 1)
        if eligibility_state != "target" or missing_gap is not None:
            return estimated_priority(
                score,
                label=strongest["label"],
                reason=strongest["reason"],
            )
        return {
            "state": "candidate",
            "score": score,
            "label": strongest["label"],
            "confidence": "verified",
            "reason": strongest["reason"],
        }

    needs_review = [item for item in considered if item["state"] == "review"]
    if eligibility_state != "target" or needs_review or not considered:
        reasons = [item["reason"] for item in needs_review]
        no_website_signal = not has_website_url or status_value in {"", "not_listed", "missing"}
        return estimated_priority(
            ESTIMATED_NO_WEBSITE_SCORE
            if no_website_signal
            else ESTIMATED_WEBSITE_UPGRADE_SCORE,
            label=(
                "Estimated missing-website potential"
                if no_website_signal
                else "Estimated website-upgrade potential"
            ),
            reason=" ".join(reasons)
            or "Website evidence is incomplete; priority is estimated from the available footprint.",
        )

    measured_scores = [
        float(item["score"])
        for item in considered
        if item.get("score") is not None
    ]
    score = round(max(measured_scores, default=0.0), 1)
    return {
        "state": "healthy",
        "score": score,
        "label": "Website appears healthy",
        "confidence": "measured",
        "reason": "Available website checks did not cross the upgrade threshold.",
    }


def _opportunity_groups(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for opportunity in opportunities:
        group_key, group_label = OPPORTUNITY_GROUPS.get(
            opportunity["key"],
            (opportunity["key"], opportunity["label"]),
        )
        group = grouped.setdefault(
            group_key,
            {
                "key": group_key,
                "label": group_label,
                "attributes": [],
            },
        )
        group["attributes"].append(opportunity)
    result = []
    for group in grouped.values():
        attributes = group["attributes"]
        verified = [item for item in attributes if item["state"] == "gap"]
        needs_review = [
            item for item in attributes if item["state"] == "review"
        ]
        state = (
            "gap"
            if verified
            else "review"
            if needs_review
            else "healthy"
        )
        last_evaluated_at = max(
            (
                item["observed_at"]
                for item in attributes
                if item.get("observed_at")
            ),
            default=None,
        )
        result.append(
            {
                **group,
                "state": state,
                "reasons": [item["label"] for item in verified]
                or [item["label"] for item in needs_review],
                # A group can contain both measured findings and checks that
                # still need evidence. Keep that coverage explicit so a
                # partial grade is never presented as comprehensive.
                "evaluated_count": len(attributes) - len(needs_review),
                "total_count": len(attributes),
                "review_reasons": [item["label"] for item in needs_review],
                "last_evaluated_at": last_evaluated_at,
            }
        )
    return result


def _admin_evidence_freshness(observed_at, expires_at) -> float:
    if expires_at is None:
        return 1.0
    now = utcnow()
    observed = observed_at
    expiry = expires_at
    if isinstance(observed, str):
        observed = datetime.fromisoformat(observed)
    if isinstance(expiry, str):
        expiry = datetime.fromisoformat(expiry)
    if observed is not None and observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= now:
        return 0.0
    if observed is None or expiry <= observed:
        return 1.0
    lifetime = (expiry - observed).total_seconds()
    remaining = (expiry - now).total_seconds()
    return max(0.0, min(1.0, remaining / lifetime))


def _attribute_data_quality_score(
    fact_attributes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize evidence quality directly from consolidated attributes."""
    operational_fact = next(
        (item for item in fact_attributes if item["key"] == "business_operational"),
        None,
    )
    operational_status = (
        "missing"
        if operational_fact is None
        else "passed"
        if operational_fact["value"] is True
        and operational_fact["evidence_state"] == "usable"
        else "failed"
        if operational_fact["value"] is False
        and operational_fact["evidence_state"] == "usable"
        else "refresh_required"
        if operational_fact["evidence_state"] == "expired"
        else "uncertain"
    )
    operational_score = (
        100
        if operational_status == "passed"
        else 0
        if operational_status == "failed"
        else None
    )
    operational_component = {
        "key": "business_operational",
        "label": "Operational status",
        "score": operational_score,
        "status": operational_status,
        "confidence": (
            operational_fact["evidence_confidence"]
            if operational_fact is not None
            else None
        ),
        "required": False,
    }
    usable_attributes = [
        item for item in fact_attributes if item["evidence_state"] == "usable"
    ]
    score = (
        0
        if operational_status == "failed"
        else round(
            sum(int(item["evidence_confidence"]) for item in usable_attributes)
            / len(usable_attributes)
        )
        if usable_attributes
        else None
    )
    if score is not None:
        score = min(max(score, 0), 100)
    label = (
        "refresh_required"
        if score is None and operational_status == "refresh_required"
        else "missing_evidence"
        if score is None
        else "reliable"
        if score >= 85
        else "review"
        if score >= 65
        else "poor"
    )
    limitations = []
    quality_reasons = []
    for component in [operational_component]:
        component_key = str(component["key"]).upper()
        if component["status"] == "passed":
            quality_reasons.append(
                {
                    "code": f"{component_key}_PASSED",
                    "impact": "positive",
                    "severity": "info",
                    "check": component["key"],
                    "score": component["score"],
                    "message": (
                        f'{component["label"]} passed'
                        + (
                            f' with {component["confidence"]}% confidence.'
                            if component["confidence"] is not None
                            else "."
                        )
                    ),
                }
            )
            continue
        if component["key"] == "business_operational" and component["status"] != "failed":
            quality_reasons.append(
                {
                    "code": "BUSINESS_OPERATIONAL_UNKNOWN",
                    "impact": "neutral",
                    "severity": "info",
                    "check": component["key"],
                    "score": None,
                    "message": "Operational status is unverified; no closure was reported.",
                }
            )
            continue
        if component["status"] == "refresh_required":
            message = f'{component["label"]} evidence requires refresh.'
            limitations.append(message.removesuffix("."))
            severity = "warning"
        elif component["status"] == "missing":
            message = f'{component["label"]} evidence is missing.'
            limitations.append(message.removesuffix("."))
            severity = "critical"
        else:
            message = f'{component["label"]} evidence is {component["status"]}.'
            limitations.append(message.removesuffix("."))
            severity = "critical" if component["status"] == "failed" else "warning"
        quality_reasons.append(
            {
                "code": f'{component_key}_{str(component["status"]).upper()}',
                "impact": "negative",
                "severity": severity,
                "check": component["key"],
                "score": component["score"],
                "message": message,
            }
        )
    limitations.extend(
        f'{item["label"]} evidence is {item["evidence_state"]}'
        for item in fact_attributes
        if item["evidence_state"] != "usable"
        and item["key"] != "business_operational"
    )
    return {
        "data_quality_score": score,
        "data_quality_label": label,
        "data_quality_breakdown": {
            "informational_checks": [operational_component],
            "opportunity_scores": fact_attributes,
            "scored_attribute_count": sum(
                item["score"] is not None for item in fact_attributes
            ),
            "attribute_count": len(fact_attributes),
            "limitations": limitations,
            "quality_reasons": quality_reasons,
        },
    }


def _attribute_component(
    key: str,
    label: str,
    score: int | None,
    weight: float,
    basis: str,
) -> dict[str, Any]:
    bounded = min(max(int(score), 0), 100) if score is not None else None
    return {
        "key": key,
        "label": label,
        "score": bounded,
        "weight": weight,
        "basis": basis,
        "label_state": (
            "unscored" if bounded is None
            else "strong" if bounded >= 80
            else "moderate" if bounded >= 50
            else "low"
        ),
    }


def _fact_attribute_component(
    fact: BusinessAttributeModel,
    *,
    now,
) -> dict[str, Any]:
    has_source = bool(fact.source_content_hash or fact.source or fact.source_url)
    expires_at = fact.expires_at
    comparable_expiry = (
        expires_at
        if expires_at is None or expires_at.tzinfo is not None
        else expires_at.replace(tzinfo=timezone.utc)
    )
    is_fresh = comparable_expiry is None or comparable_expiry >= now
    is_confirmed = fact.resolution_state == "confirmed"
    confidence = min(max(int(fact.confidence), 0), 100)
    score = fact.attribute_score
    if score is None:
        score = score_attribute(fact.attribute_key, _attribute_value(fact)).score
    evidence_state = (
        "usable"
        if has_source and is_fresh and is_confirmed
        else "rejected"
        if fact.resolution_state == "rejected"
        else "source missing"
        if not has_source
        else "expired"
        if not is_fresh
        else "conflicted"
        if not is_confirmed
        else "staged"
    )
    basis = ", ".join(
        [
            fact.score_reason or "opportunity score",
            f"{confidence}% evidence confidence",
            "source linked" if has_source else "source missing",
            "fresh" if is_fresh else "expired",
            fact.resolution_state,
        ]
    )
    component = _attribute_component(
        fact.attribute_key,
        fact.attribute_key.replace("_", " ").title(),
        round(score) if score is not None else None,
        0,
        basis,
    )
    component.update(
        {
            "value": _attribute_value(fact),
            "evidence_confidence": confidence,
            "evidence_state": evidence_state,
            "resolution_state": fact.resolution_state,
            "quality_state": "usable" if evidence_state == "usable" else evidence_state,
            "source_evidence_id": (fact.supporting_evidence_ids or [None])[0],
            "observed_at": fact.observed_at,
            "expires_at": fact.expires_at,
        }
    )
    return component


def _business_dict(business: BusinessModel) -> dict[str, Any]:
    return {
        "display_name": business.display_name,
        "website_url": business.website_url,
        "domain": business.domain,
        "phone": business.phone,
        "address": business.address,
        "geography": business.geography,
        "market_key": business.market_key,
        "latitude": business.latitude,
        "longitude": business.longitude,
        "customer_kind": business.customer_kind,
        "is_chain": business.is_chain,
        "is_franchise": business.is_franchise,
        "is_directory": business.is_directory,
        "is_agency": business.is_agency,
        "status": business.status,
    }


def _signal_definition_dict(definition: SignalDefinitionModel) -> dict[str, Any]:
    return {
        "id": definition.id,
        "key": definition.key,
        "label": definition.label,
        "description": definition.description,
        "value_type": definition.value_type,
        "category": definition.category,
        "unit": definition.unit,
        "status": definition.status,
        "collector_key": definition.collector_key,
        "extractor_key": definition.extractor_key,
        "freshness_days": definition.freshness_days,
        "opportunity_direction": definition.opportunity_direction,
        "config": definition.config or {},
        "version": definition.version,
        "created_at": definition.created_at.isoformat() if definition.created_at else None,
        "updated_at": definition.updated_at.isoformat() if definition.updated_at else None,
    }


def _service_definition_dict(definition: ServiceDefinitionModel) -> dict[str, Any]:
    return {
        "id": definition.id,
        "key": definition.key,
        "label": definition.label,
        "description": definition.description,
        "status": definition.status,
        "sort_order": definition.sort_order,
        "version": definition.version,
        "signals": [
            {
                "definition_id": mapping.signal_definition.id,
                "key": mapping.signal_definition.key,
                "label": mapping.signal_definition.label,
                "status": mapping.signal_definition.status,
                "weight": mapping.weight,
            }
            for mapping in sorted(
                definition.signal_mappings,
                key=lambda item: item.sort_order,
            )
        ],
        "created_at": definition.created_at.isoformat() if definition.created_at else None,
        "updated_at": definition.updated_at.isoformat() if definition.updated_at else None,
    }


def _payload_value(payload: Any, keys: set[str]) -> Any:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in keys and _payload_value_present(value):
                return value
        for value in payload.values():
            found = _payload_value(value, keys)
            if _payload_value_present(found):
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _payload_value(value, keys)
            if _payload_value_present(found):
                return found
    return None


def _payload_has(payload: Any, keys: set[str]) -> bool:
    return _payload_value(payload, keys) is not None


def _payload_value_present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _attribute_value(fact: BusinessAttributeModel) -> Any:
    if fact.value_type == "boolean":
        return fact.value_boolean
    if fact.value_type == "number":
        return fact.value_number
    return fact.value_text


def _attribute_lineage_dict(
    attribute: BusinessAttributeModel,
    definition: SignalDefinitionModel | None,
    mappings_by_definition: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    value = _attribute_value(attribute)
    matches_opportunity = bool(
        definition is not None and _fact_matches_opportunity(definition, value)
    )
    minimum_confidence = int(
        (
            (definition.config or {}).get(
                "minimum_confidence", DEFAULT_MINIMUM_FACT_CONFIDENCE
            )
        )
        if definition is not None
        else 90
    )
    eligible = bool(
        matches_opportunity
        and definition is not None
        and definition.status == "active"
        and attribute.resolution_state == "confirmed"
        and bool(
            attribute.source_content_hash
            or attribute.source
            or attribute.source_url
        )
        and attribute.confidence >= minimum_confidence
        and not _datetime_is_past(attribute.expires_at)
    )
    return {
        "id": attribute.id,
        "key": attribute.attribute_key,
        "value": value,
        "value_type": attribute.value_type,
        "opportunity_score": attribute.attribute_score,
        "score_version": attribute.score_version,
        "score_reason": attribute.score_reason,
        "evidence_confidence": attribute.confidence,
        "confidence": attribute.confidence,
        "resolution_state": attribute.resolution_state,
        "evidence_state": "usable" if eligible else attribute.resolution_state,
        "observed_at": attribute.observed_at,
        "expires_at": attribute.expires_at,
        "source_evidence_id": (attribute.supporting_evidence_ids or [None])[0],
        "supporting_evidence_ids": list(attribute.supporting_evidence_ids or []),
        "signal": (
            {
                "definition_id": definition.id,
                "key": definition.key,
                "label": definition.label,
                "category": definition.category,
                "status": definition.status,
                "opportunity_direction": definition.opportunity_direction,
                "matches_opportunity_value": matches_opportunity,
                "eligible_for_matching": eligible,
                "services": mappings_by_definition.get(definition.id, []),
            }
            if definition is not None
            else None
        ),
    }


def _fact_matches_opportunity(
    definition: SignalDefinitionModel,
    value: Any,
) -> bool:
    direction = definition.opportunity_direction
    config = definition.config or {}
    if direction == "false_is_opportunity":
        return value is False
    if direction == "true_is_opportunity":
        return value is True
    threshold = config.get("opportunity_threshold")
    if direction == "lower_is_opportunity":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
            and float(value) < float(threshold)
        )
    if direction == "higher_is_opportunity":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
            and float(value) > float(threshold)
        )
    if direction == "missing_is_opportunity":
        values = config.get("opportunity_values") or [
            "missing",
            "unavailable",
            "parked",
        ]
        return value in values
    return False


def _business_signal_dict(
    definition: SignalDefinitionModel,
    fact: BusinessAttributeModel | None,
) -> dict[str, Any]:
    status = "missing"
    if fact is not None:
        status = "stale" if _datetime_is_past(fact.expires_at) else "current"
    return {
        "definition_id": definition.id,
        "key": definition.key,
        "label": definition.label,
        "category": definition.category,
        "value_type": definition.value_type,
        "unit": definition.unit,
        "status": status,
        "value": _attribute_value(fact) if fact is not None else None,
        "confidence": fact.confidence if fact is not None else None,
        "evidence_state": fact.resolution_state if fact is not None else None,
        "observed_at": fact.observed_at if fact is not None else None,
        "expires_at": fact.expires_at if fact is not None else None,
    }


def _datetime_is_past(value: datetime | None) -> bool:
    if value is None:
        return False
    comparable = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return comparable <= utcnow()
