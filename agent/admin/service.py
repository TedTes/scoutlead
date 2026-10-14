from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
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
from canonical.normalization import normalize_business_name, normalize_domain, normalize_phone
from db.base import Base
from db.models import (
    AdminAuditEventModel,
    BusinessFactModel,
    BusinessIndexSegmentModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    BusinessPublicationModel,
    NicheModel,
    QueueJobModel,
    ServiceDefinitionModel,
    ServiceSignalMappingModel,
    SignalDefinitionModel,
    SourceItemModel,
    ValidationResultModel,
)
from publication.validation import BusinessValidationService
from job_queue.schemas import JobStatus, JobType
from job_queue.service import QueueService
from shared.errors import ConflictError, NotFoundError, ValidationError
from shared.utils import new_id, normalize_url, utcnow
from service_definitions.repository import ServiceDefinitionRepository
from signal_definitions.repository import SignalDefinitionRepository
from source_items.repository import SourceItemRepository, source_item_content_hash
from source_items.schemas import (
    SourceItemCreate,
    SourceItemDecisionCreate,
    SourceItemDecisionValue,
    SourceItemStage,
    SourceItemState,
)


REQUIRED_VALIDATIONS = {"identity", "business_identity", "trade", "location"}
SOURCE_PRIORITY = {
    "google_places": 0,
    "google_places_seed": 1,
    "company_website_seed": 2,
    "openstreetmap_seed": 3,
    "configured_search": 4,
    "website_presence_check": 5,
    "admin_manual": 6,
    "kijiji": 7,
}


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
                    select(BusinessFactModel.id)
                    .where(
                        BusinessFactModel.signal_definition_id
                        == mapping.signal_definition_id,
                        BusinessFactModel.quality_state == "published",
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
        statement = select(BusinessFactModel).where(
            BusinessFactModel.signal_definition_id == definition.id,
            BusinessFactModel.quality_state == "staged",
        )
        if scope == "selected":
            statement = statement.where(BusinessFactModel.business_id.in_(selected_ids))
        facts = list(self.session.scalars(statement))
        quality_state = "published" if decision == "approve" else "rejected"
        for fact in facts:
            fact.quality_state = quality_state
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
            raise ConflictError("Collection must finish before validation can start")
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
            original_state = item.state
            item.state = SourceItemState.VALIDATION_QUEUED.value
            if original_state == SourceItemState.RELEVANT.value:
                queue.enqueue_business_identity_resolve(
                    source_item_id=item.id,
                    segment_id=item.segment_id,
                )
            else:
                queue.enqueue_source_item_classify(
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
        businesses = list(self.session.scalars(select(BusinessModel)))
        states = self._validation_states([business.id for business in businesses])
        status_counts = Counter(business.status for business in businesses)
        validation_counts = Counter(states[business.id]["state"] for business in businesses)
        return {
            "total": len(businesses),
            "active": status_counts["active"],
            "quarantined": status_counts["quarantined"],
            "archived": status_counts["archived"],
            "fully_validated": validation_counts["passed"],
            "needs_attention": validation_counts["attention"],
            "incomplete": validation_counts["incomplete"],
            "published": self.session.scalar(
                select(func.count()).select_from(BusinessPublicationModel).where(
                    BusinessPublicationModel.status == "published"
                )
            ) or 0,
        }

    def queue_publication_evaluation(
        self,
        *,
        reason: str,
        scope: str,
        business_ids: list[str],
    ) -> dict[str, Any]:
        requested_ids = list(dict.fromkeys(business_ids))
        if scope == "selected" and not requested_ids:
            raise ValidationError("Select at least one business")

        statement = select(BusinessModel).where(BusinessModel.status == "active")
        if scope == "selected":
            found_ids = set(
                self.session.scalars(
                    select(BusinessModel.id).where(BusinessModel.id.in_(requested_ids))
                )
            )
            unknown_ids = set(requested_ids) - found_ids
            if unknown_ids:
                raise ValidationError(
                    "One or more selected businesses do not exist",
                    {"business_ids": sorted(unknown_ids)},
                )
            statement = statement.where(BusinessModel.id.in_(requested_ids))

        businesses = list(self.session.scalars(statement))
        states = self._validation_states([business.id for business in businesses])
        eligible_ids = {
            business.id
            for business in businesses
            if states[business.id]["state"] == "passed"
        }
        scope_rows = list(
            self.session.execute(
                select(BusinessNicheMembershipModel, BusinessIndexSegmentModel)
                .join(
                    BusinessIndexSegmentModel,
                    and_(
                        BusinessIndexSegmentModel.niche_id
                        == BusinessNicheMembershipModel.niche_id,
                        BusinessIndexSegmentModel.market_key
                        == BusinessNicheMembershipModel.market_key,
                    ),
                )
                .where(
                    BusinessNicheMembershipModel.business_id.in_(eligible_ids),
                    BusinessIndexSegmentModel.status == "active",
                )
                .order_by(
                    BusinessNicheMembershipModel.business_id,
                    BusinessNicheMembershipModel.confidence.desc(),
                )
            )
        ) if eligible_ids else []

        queue = QueueService(self.session)
        evaluated_business_ids: set[str] = set()
        queued_scopes: set[tuple[str, str]] = set()
        for membership, segment in scope_rows:
            scope_key = (membership.business_id, segment.id)
            if scope_key in queued_scopes:
                continue
            queue.enqueue_business_publication_evaluate(
                source_item_id=None,
                segment_id=segment.id,
                business_id=membership.business_id,
                commit=False,
            )
            queued_scopes.add(scope_key)
            evaluated_business_ids.add(membership.business_id)

        batch_id = new_id("publication_evaluation")
        requested_count = len(requested_ids) if scope == "selected" else len(businesses)
        result = {
            "batch_id": batch_id,
            "requested_business_count": requested_count,
            "eligible_business_count": len(eligible_ids),
            "queued_evaluation_count": len(queued_scopes),
            "skipped_business_count": requested_count - len(evaluated_business_ids),
        }
        self._audit(
            "publication:evaluate",
            batch_id,
            reason,
            None,
            {**result, "scope": scope},
            entity_type="publication_evaluation",
        )
        self.session.commit()
        return result

    def list_businesses(
        self,
        *,
        query: str | None,
        validation: str | None,
        status: str | None,
        niche_slug: str | None,
        market_key: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        statement = select(BusinessModel)
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
        if niche_slug or market_key:
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
        states = self._validation_states([business.id for business in businesses])
        memberships = self._primary_memberships([business.id for business in businesses])
        rows = [
            self._business_summary(business, states[business.id], memberships.get(business.id))
            for business in businesses
        ]
        if validation:
            rows = [row for row in rows if row["validation_state"] == validation]
        total = len(rows)
        start = (page - 1) * page_size
        return {
            "items": rows[start : start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def detail(self, business_id: str) -> dict[str, Any]:
        business = self._business(business_id)
        state = self._validation_states([business_id])[business_id]
        memberships = list(
            self.session.execute(
                select(BusinessNicheMembershipModel, NicheModel)
                .join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
                .where(BusinessNicheMembershipModel.business_id == business_id)
            )
        )
        facts = list(
            self.session.scalars(
                select(BusinessFactModel)
                .where(BusinessFactModel.business_id == business_id)
                .order_by(BusinessFactModel.fact_key)
            )
        )
        active_signals = SignalDefinitionRepository(self.session).list(status="active")
        facts_by_definition = {
            fact.signal_definition_id: fact
            for fact in facts
            if fact.signal_definition_id is not None
        }
        facts_by_key = {fact.fact_key: fact for fact in facts}
        sources = list(
            self.session.scalars(
                select(SourceItemModel)
                .where(SourceItemModel.business_id == business_id)
                .order_by(SourceItemModel.fetched_at.desc())
                .limit(30)
            )
        )
        publications = list(
            self.session.scalars(
                select(BusinessPublicationModel)
                .where(BusinessPublicationModel.business_id == business_id)
                .order_by(BusinessPublicationModel.evaluated_at.desc())
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
        return {
            **self._business_summary(business, state, memberships[0] if memberships else None),
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
            "validations": state["validations"],
            "facts": [
                {
                    "id": fact.id,
                    "key": fact.fact_key,
                    "value": _fact_value(fact),
                    "confidence": fact.confidence,
                    "resolution_state": fact.resolution_state,
                    "quality_state": fact.quality_state,
                    "observed_at": fact.observed_at,
                    "expires_at": fact.expires_at,
                }
                for fact in facts
            ],
            "signals": [
                _business_signal_dict(
                    definition,
                    facts_by_definition.get(definition.id)
                    or facts_by_key.get(definition.key),
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
            "publications": [
                {
                    "id": publication.id,
                    "niche_id": publication.niche_id,
                    "market_key": publication.market_key,
                    "status": publication.status,
                    "reasons": publication.reasons,
                    "evaluated_at": publication.evaluated_at,
                    "expires_at": publication.expires_at,
                }
                for publication in publications
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
        BusinessValidationService(self.session).validate(business=business, source_item=source, segment=segment)
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
        self._withdraw_publications(business.id, "quarantined")
        self._audit("update", business.id, data.reason, before, _business_dict(business))
        self.session.commit()
        return self.detail(business.id)

    def change_status(self, business_id: str, status: str, reason: str) -> dict[str, Any]:
        business = self._business(business_id)
        before = _business_dict(business)
        business.status = status
        if status != "active":
            self._withdraw_publications(business.id, status)
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
        results = BusinessValidationService(self.session).validate(
            business=business, source_item=source, segment=segment
        )
        statuses = {result.status for result in results}
        source.state = (
            "rejected"
            if "failed" in statuses
            else "needs_review"
            if statuses != {"passed"}
            else "validated"
        )
        if statuses == {"passed"}:
            QueueService(self.session).enqueue_business_publication_evaluate(
                source_item_id=source.id,
                segment_id=segment.id,
                business_id=business.id,
                commit=False,
            )
        self._audit(
            "revalidate",
            business.id,
            reason,
            None,
            {"source_item_id": source.id, "results": {r.validation_type: r.status for r in results}},
        )
        self.session.commit()
        return self.detail(business.id)

    def delete_dependencies(self, business_id: str) -> dict[str, int]:
        self._business(business_id)
        dependencies: dict[str, int] = {}
        for table in Base.metadata.sorted_tables:
            if table.name in {"businesses", "admin_audit_events"}:
                continue
            columns = [
                column for column in table.columns
                if any(fk.column.table.name == "businesses" for fk in column.foreign_keys)
            ]
            if not columns:
                continue
            count = 0
            for column in columns:
                count += int(self.session.scalar(select(func.count()).select_from(table).where(column == business_id)) or 0)
            if count:
                dependencies[table.name] = count
        return dependencies

    def delete(self, business_id: str, confirmation: str, reason: str) -> None:
        business = self._business(business_id)
        if confirmation.strip() != business.display_name:
            raise ValidationError("Confirmation must exactly match the business name")
        dependencies = self.delete_dependencies(business_id)
        if dependencies:
            raise ConflictError(
                "Permanent deletion is blocked because related records exist. Archive the business instead.",
                {"dependencies": dependencies},
            )
        before = _business_dict(business)
        self._audit("delete", business.id, reason, before, None)
        self.session.delete(business)
        self.session.commit()

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
            SourceItemState.VALIDATION_QUEUED.value,
            SourceItemState.IDENTITY_RESOLVED.value,
            SourceItemState.VALIDATING.value,
            SourceItemState.AUDIT_PENDING.value,
        }
        validated_states = {
            SourceItemState.VALIDATED.value,
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
                    SourceItemState.VALIDATION_QUEUED.value,
                    SourceItemState.IDENTITY_RESOLVED.value,
                    SourceItemState.VALIDATING.value,
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
                SourceItemState.VALIDATION_QUEUED.value,
                SourceItemState.IDENTITY_RESOLVED.value,
                SourceItemState.VALIDATING.value,
                SourceItemState.AUDIT_PENDING.value,
            }
        ):
            return "validating"
        return "completed"

    def _validation_states(self, business_ids: list[str]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, ValidationResultModel]] = defaultdict(dict)
        if business_ids:
            rows = list(
                self.session.scalars(
                    select(ValidationResultModel)
                    .where(
                        ValidationResultModel.business_id.in_(business_ids),
                        ValidationResultModel.expires_at >= utcnow(),
                    )
                    .order_by(ValidationResultModel.observed_at.desc())
                )
            )
            for row in rows:
                grouped[row.business_id].setdefault(row.validation_type, row)
        result: dict[str, dict[str, Any]] = {}
        for business_id in business_ids:
            validations = grouped[business_id]
            required = {key: validations.get(key) for key in REQUIRED_VALIDATIONS}
            statuses = {row.status for row in required.values() if row is not None}
            state = (
                "incomplete"
                if any(row is None for row in required.values())
                else "passed"
                if statuses == {"passed"}
                else "attention"
            )
            result[business_id] = {
                "state": state,
                "validations": [
                    {
                        "id": row.id,
                        "type": row.validation_type,
                        "status": row.status,
                        "confidence": row.confidence,
                        "reason": row.reason,
                        "evidence": row.evidence,
                        "observed_at": row.observed_at,
                        "expires_at": row.expires_at,
                    }
                    for row in required.values()
                    if row is not None
                ],
            }
        return result

    def _business_summary(
        self,
        business: BusinessModel,
        state: dict[str, Any],
        membership=None,
    ) -> dict[str, Any]:
        return {
            "id": business.id,
            "display_name": business.display_name,
            "status": business.status,
            "validation_state": state["state"],
            "website_url": business.website_url,
            "domain": business.domain,
            "phone": business.phone,
            "address": business.address,
            "geography": business.geography,
            "market_key": membership[0].market_key if membership else business.market_key,
            "niche_slug": membership[1].slug if membership else business.category_key,
            "niche_label": membership[1].label if membership else business.category_key,
            "last_seen_at": business.last_seen_at,
        }

    def _primary_memberships(self, business_ids: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if not business_ids:
            return result
        rows = self.session.execute(
            select(BusinessNicheMembershipModel, NicheModel)
            .join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
            .where(BusinessNicheMembershipModel.business_id.in_(business_ids))
            .order_by(BusinessNicheMembershipModel.confidence.desc())
        )
        for membership, niche in rows:
            result.setdefault(membership.business_id, (membership, niche))
        return result

    def _withdraw_publications(self, business_id: str, status: str) -> None:
        for publication in self.session.scalars(
            select(BusinessPublicationModel).where(
                BusinessPublicationModel.business_id == business_id,
                BusinessPublicationModel.status == "published",
            )
        ):
            publication.status = status
            publication.reasons = [
                *(publication.reasons or []),
                {"code": "admin_withdrawal", "message": f"Business set to {status}."},
            ]
            publication.evaluated_at = utcnow()

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


def _fact_value(fact: BusinessFactModel) -> Any:
    if fact.value_type == "boolean":
        return fact.value_boolean
    if fact.value_type == "number":
        return fact.value_number
    return fact.value_text


def _business_signal_dict(
    definition: SignalDefinitionModel,
    fact: BusinessFactModel | None,
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
        "value": _fact_value(fact) if fact is not None else None,
        "confidence": fact.confidence if fact is not None else None,
        "quality_state": fact.quality_state if fact is not None else None,
        "observed_at": fact.observed_at if fact is not None else None,
        "expires_at": fact.expires_at if fact is not None else None,
    }


def _datetime_is_past(value: datetime | None) -> bool:
    if value is None:
        return False
    comparable = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return comparable <= utcnow()
