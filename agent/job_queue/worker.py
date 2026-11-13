from datetime import date, datetime, timezone
from time import monotonic, sleep

from sqlalchemy import select
from sqlalchemy.orm import Session

from audience_runs.service import AudienceRunService
from app.config import get_settings
from app.dependencies import AppServices, create_app_services
from app.service_factory import (
    business_index_pipeline_service,
    campaign_service,
)
from business_index.scheduler import enqueue_due_business_index_refreshes
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignStatus
from campaigns.service import CampaignService
from db.session import create_database
from db.models import (
    CampaignModel,
    QueueJobModel,
    TerritoryModel,
)
from job_queue.repository import QueueRepository
from job_queue.schemas import JobStatus, JobType
from job_queue.service import QueueService
from messages.service import MessageService
from signal_collection.service import SignalCollectionService
from signal_collection.scheduler import enqueue_due_signal_collections
from products.repository import ProductRepository
from source_requests.service import SourceRequestService
from outcomes.maintenance import run_outcome_maintenance
from shared.logger import configure_logging, get_logger
from territories.scheduler import enqueue_due_territories

logger = get_logger(__name__)
_last_territory_scheduler_tick = 0.0
_last_business_index_scheduler_tick = 0.0
_last_outcome_maintenance_date: date | None = None
_last_evidence_expiry_tick = 0.0
_last_signal_collection_tick = 0.0


def run_once() -> bool:
    # Keep this entrypoint minimal for the Railway worker process.
    settings = get_settings()
    configure_logging(settings.log_level)
    services = create_app_services(settings)
    create_database(services.db.engine)

    generator = services.db.session()
    session = next(generator)
    try:
        _scheduler_tick(session, services)
        queue = QueueRepository(session)
        job = queue.claim_next()
        if job is None:
            return False
        logger.info(
            "job_started job_id=%s job_type=%s attempt=%s",
            job.id,
            job.type,
            job.attempts,
        )
        # Capture queue metadata before executing the job. A failed flush expires
        # ORM attributes and leaves the transaction aborted, so even reading
        # ``job.id`` in the exception handler can otherwise raise a second error
        # and terminate the worker process.
        job_id = job.id
        job_type = job.type
        job_payload = dict(job.payload or {})
        try:
            _execute_job(session, services, job)
        except Exception as exc:
            logger.exception("job_failed job_id=%s", job_id)
            # A database error leaves PostgreSQL transactions aborted.  Reset
            # the failed unit of work before trying to persist the queue retry
            # or dead-letter state; otherwise queue.fail() raises
            # InFailedSqlTransaction and terminates the worker.
            session.rollback()
            failed_job = queue.fail(
                job_id,
                str(exc),
                retry_delay_seconds=None,
            )
            if failed_job.status in {
                JobStatus.FAILED.value,
                JobStatus.DEAD_LETTER.value,
            } and job_payload.get("source_item_id"):
                _record_source_item_failure(
                    session,
                    source_item_id=str(job_payload["source_item_id"]),
                    job_type=str(job_type),
                    reason=str(exc),
                )
            if (
                failed_job.status in {JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value}
                and job_type == JobType.BUSINESS_INDEX_REFRESH.value
            ):
                _fail_expanding_campaigns(
                    session,
                    segment_id=str(job_payload["segment_id"]),
                    reason=str(exc),
                )
            if (
                failed_job.status in {JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value}
                and job_type == JobType.AUDIENCE_RUN.value
            ):
                _fail_audience_run(
                    session,
                    run_id=str(job_payload["audience_run_id"]),
                    reason=str(exc),
                )
            return True
        queue.complete(job_id)
        logger.info("job_completed job_id=%s job_type=%s", job_id, job_type)
        return True
    finally:
        generator.close()


def _execute_job(
    session: Session,
    services: AppServices,
    job: QueueJobModel,
) -> None:
    if job.type == JobType.MESSAGE_SEND.value:
        MessageService(session=session, email=services.email).send(
            str(job.payload["message_id"])
        )
    elif job.type == JobType.AUDIENCE_RUN.value:
        audience = session.get(
            TerritoryModel,
            str(job.payload["audience_run_id"]),
        )
        if audience is None:
            raise ValueError(
                f"saved search not found: {job.payload['audience_run_id']}"
            )
        AudienceRunService(
            session,
            workspace_id=audience.workspace_id,
        ).process(audience.id)
    elif job.type == JobType.BUSINESS_INDEX_REFRESH.value:
        business_index_pipeline_service(
            session=session,
            services=services,
        ).plan_refresh(
            str(job.payload["segment_id"]),
            processing_mode=str(job.payload.get("processing_mode", "automatic")),
            parent_job_id=job.id,
        )
    elif job.type == JobType.SOURCE_FETCH.value:
        business_index_pipeline_service(
            session=session,
            services=services,
        ).fetch_source(
            str(job.payload["segment_id"]),
            source_index=int(job.payload["source_index"]),
            task_data=dict(job.payload["task"]),
            job_id=job.id,
            processing_mode=str(job.payload.get("processing_mode", "automatic")),
        )
    elif job.type == JobType.BUSINESS_IDENTITY_RESOLVE.value:
        business_index_pipeline_service(
            session=session,
            services=services,
        ).resolve_identity(str(job.payload["source_item_id"]))
    elif job.type == JobType.BUSINESS_OPPORTUNITY_AUDIT.value:
        business_index_pipeline_service(
            session=session,
            services=services,
        ).audit_opportunity(
            (
                str(job.payload["source_item_id"])
                if job.payload.get("source_item_id")
                else None
            ),
            business_id=str(job.payload["business_id"]),
            segment_id=str(job.payload["segment_id"]),
            job_id=job.id,
        )
    elif job.type == JobType.SIGNAL_COLLECTION.value:
        SignalCollectionService(
            session,
            timeout_seconds=services.settings.request_timeout_seconds,
            browser_render_endpoint=services.settings.browser_render_endpoint,
            browser_render_api_key=services.settings.browser_render_api_key,
            pagespeed_api_key=services.settings.pagespeed_api_key,
            pagespeed_api_endpoint=services.settings.pagespeed_api_endpoint,
        ).collect(
            str(job.payload["signal_definition_id"]),
            expected_version=int(job.payload["signal_version"]),
            business_ids=_job_business_ids(job),
        )
    else:
        raise ValueError(f"unknown job type: {job.type}")


def _job_business_ids(job: QueueJobModel) -> list[str]:
    return [str(value) for value in job.payload.get("business_ids", [])]


def run() -> None:
    _recover_interrupted_jobs()
    while True:
        did_work = run_once()
        if not did_work:
            sleep(2)


def _source_request_service(
    session: Session,
    services: AppServices,
) -> SourceRequestService:
    return SourceRequestService(
        products=ProductRepository(session),
        campaigns=_campaign_service(session=session, services=services),
        llm=services.llm,
        google_places_configured=bool(services.settings.google_places_api_key),
        search_configured=services.search.is_configured,
        openstreetmap_enabled=services.settings.openstreetmap_enabled,
        apify_source_provider_id=services.settings.apify_source_provider_id,
        apify_source_label=services.settings.apify_source_label,
        apify_sources=services.settings.apify_source_configs,
        source_recipes=services.settings.source_template_configs,
    )


def _recover_interrupted_jobs() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    services = create_app_services(settings)
    create_database(services.db.engine)
    generator = services.db.session()
    session = next(generator)
    try:
        recovered = QueueRepository(session).recover_stale_running()
        for job in recovered:
            if job.status in {
                JobStatus.FAILED.value,
                JobStatus.DEAD_LETTER.value,
            } and job.payload.get("source_item_id"):
                _record_source_item_failure(
                    session,
                    source_item_id=str(job.payload["source_item_id"]),
                    job_type=str(job.type),
                    reason=job.last_error or "Background stage stopped before completion.",
                )
            if (
                job.status in {JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value}
                and job.type == JobType.BUSINESS_INDEX_REFRESH.value
            ):
                _fail_expanding_campaigns(
                    session,
                    segment_id=str(job.payload["segment_id"]),
                    reason=job.last_error or "Background discovery stopped before completion.",
                )
            if (
                job.status in {JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value}
                and job.type == JobType.AUDIENCE_RUN.value
                and job.payload.get("audience_run_id")
            ):
                _fail_audience_run(
                    session,
                    run_id=str(job.payload["audience_run_id"]),
                    reason=job.last_error
                    or "Audience matching stopped before completion.",
                )
        if recovered:
            logger.warning("recovered_stale_jobs count=%s", len(recovered))
    finally:
        generator.close()


def _fail_expanding_campaigns(session: Session, *, segment_id: str, reason: str) -> None:
    campaigns = CampaignRepository(session)
    rows = session.query(CampaignModel).filter(
        CampaignModel.status == CampaignStatus.EXPANDING.value
    )
    for row in rows:
        if (row.source_inputs or {}).get("business_index_segment_id") != segment_id:
            continue
        campaigns.update_status(
            row.id,
            CampaignStatus.FAILED,
            failure_reason=reason,
            commit=False,
        )
    session.commit()


def _fail_audience_run(session: Session, *, run_id: str, reason: str) -> None:
    audience = session.get(TerritoryModel, run_id)
    if audience is None:
        return
    audience.match_state = "failed"
    audience.match_failure_reason = reason[:2000]
    audience.match_completed_at = datetime.now(timezone.utc)
    session.commit()


def _record_source_item_failure(
    session: Session,
    *,
    source_item_id: str,
    job_type: str,
    reason: str,
) -> None:
    from source_items.repository import SourceItemRepository
    from source_items.schemas import (
        SourceItemDecisionCreate,
        SourceItemDecisionValue,
        SourceItemStage,
        SourceItemState,
    )

    SourceItemRepository(session).add_decision(
        source_item_id,
        SourceItemDecisionCreate(
            stage={
                JobType.BUSINESS_IDENTITY_RESOLVE.value: SourceItemStage.IDENTITY,
                JobType.BUSINESS_OPPORTUNITY_AUDIT.value: SourceItemStage.OPPORTUNITY,
            }.get(job_type, SourceItemStage.IDENTITY),
            decision=SourceItemDecisionValue.FAILED,
            reason=reason,
        ),
        next_state=SourceItemState.FAILED,
        error=reason,
    )


def _campaign_service(*, session: Session, services: AppServices) -> CampaignService:
    return campaign_service(
        session=session,
        services=services,
        workspace_id=None,
    )


def _scheduler_tick(session: Session, services: AppServices) -> None:
    global _last_business_index_scheduler_tick
    global _last_evidence_expiry_tick
    global _last_signal_collection_tick
    global _last_outcome_maintenance_date, _last_territory_scheduler_tick
    now = monotonic()
    if (
        services.settings.business_index_scheduler_enabled
        and now - _last_business_index_scheduler_tick >= 60
    ):
        enqueue_due_business_index_refreshes(session)
        _last_business_index_scheduler_tick = now
    if now - _last_evidence_expiry_tick >= 3600:
        _last_evidence_expiry_tick = now
    if (
        services.settings.signal_collection_scheduler_enabled
        and now - _last_signal_collection_tick >= 3600
    ):
        enqueue_due_signal_collections(session, limit=50, batch_size=10)
        _last_signal_collection_tick = now
    today = datetime.now(timezone.utc).date()
    if _last_outcome_maintenance_date != today:
        run_outcome_maintenance(
            session,
            no_response_days=services.settings.no_response_days,
        )
        _last_outcome_maintenance_date = today
    if not services.settings.territory_scheduler_enabled:
        return
    if now - _last_territory_scheduler_tick < 60:
        return
    enqueue_due_territories(session)
    _last_territory_scheduler_tick = now


if __name__ == "__main__":
    run()
