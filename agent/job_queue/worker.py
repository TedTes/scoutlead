from datetime import date, datetime, time, timezone
from time import monotonic, sleep

from sqlalchemy.orm import Session

from agent_runs.repository import AgentRunRepository
from app.config import get_settings
from app.dependencies import AppServices, create_app_services
from app.service_factory import (
    business_index_pipeline_service,
    campaign_service,
    territory_refresh_service,
)
from business_index.scheduler import enqueue_due_business_index_refreshes
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignStatus
from campaigns.service import CampaignService
from db.session import create_database
from db.models import CampaignModel, TerritoryModel
from job_queue.repository import QueueRepository
from job_queue.schemas import JobStatus, JobType
from messages.service import MessageService
from outcomes.maintenance import run_outcome_maintenance
from shared.logger import configure_logging, get_logger
from territories.scheduler import enqueue_due_territories

logger = get_logger(__name__)
_last_territory_scheduler_tick = 0.0
_last_business_index_scheduler_tick = 0.0
_last_outcome_maintenance_date: date | None = None


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
            agent_run = AgentRunRepository(session).claim_next()
            if agent_run is None:
                return False
            try:
                _campaign_service(session=session, services=services).run_campaign(
                    agent_run.campaign_id,
                    agent_run_id=agent_run.id,
                )
            except Exception:
                logger.exception("agent_run_failed run_id=%s", agent_run.id)
            return True
        try:
            if job.type == JobType.CAMPAIGN_RUN.value:
                _campaign_service(session=session, services=services).run_campaign(
                    str(job.payload["campaign_id"])
                )
            elif job.type == JobType.MESSAGE_SEND.value:
                MessageService(session=session, email=services.email).send(
                    str(job.payload["message_id"])
                )
            elif job.type == JobType.TERRITORY_REFRESH.value:
                territory_id = str(job.payload["territory_id"])
                territory = session.get(TerritoryModel, territory_id)
                if territory is None:
                    raise ValueError(f"territory not found: {territory_id}")
                scheduled_for = datetime.combine(
                    date.fromisoformat(str(job.payload["scheduled_date"])),
                    time.min,
                    tzinfo=timezone.utc,
                )
                territory_refresh_service(
                    session=session,
                    services=services,
                    workspace_id=territory.workspace_id,
                ).refresh(territory_id, scheduled_for=scheduled_for)
            elif job.type == JobType.BUSINESS_INDEX_REFRESH.value:
                business_index_pipeline_service(
                    session=session,
                    services=services,
                ).plan_refresh(str(job.payload["segment_id"]))
            elif job.type == JobType.SOURCE_FETCH.value:
                business_index_pipeline_service(
                    session=session,
                    services=services,
                ).fetch_source(
                    str(job.payload["segment_id"]),
                    source_index=int(job.payload["source_index"]),
                    task_data=dict(job.payload["task"]),
                    job_id=job.id,
                )
            elif job.type == JobType.SOURCE_ITEM_CLASSIFY.value:
                business_index_pipeline_service(
                    session=session,
                    services=services,
                ).classify_source_item(
                    str(job.payload["source_item_id"]),
                    job_id=job.id,
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
            elif job.type == JobType.SEARCH_ELIGIBILITY_MATCH.value:
                business_index_pipeline_service(
                    session=session,
                    services=services,
                ).match_eligibility(
                    str(job.payload["segment_id"]),
                    job_id=job.id,
                )
            else:
                raise ValueError(f"unknown job type: {job.type}")
        except Exception as exc:
            logger.exception("job_failed job_id=%s", job.id)
            failed_job = queue.fail(
                job.id,
                str(exc),
                retry_delay_seconds=(3600 if job.type == JobType.TERRITORY_REFRESH.value else None),
            )
            if failed_job.status == JobStatus.FAILED.value and job.payload.get("source_item_id"):
                _record_source_item_failure(
                    session,
                    source_item_id=str(job.payload["source_item_id"]),
                    job_type=str(job.type),
                    reason=str(exc),
                )
            if (
                failed_job.status == JobStatus.FAILED.value
                and job.type == JobType.BUSINESS_INDEX_REFRESH.value
            ):
                _fail_expanding_campaigns(
                    session,
                    segment_id=str(job.payload["segment_id"]),
                    reason=str(exc),
                )
            return True
        queue.complete(job.id)
        return True
    finally:
        generator.close()


def run() -> None:
    _recover_interrupted_jobs()
    while True:
        did_work = run_once()
        if not did_work:
            sleep(2)


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
            if job.status == JobStatus.FAILED.value and job.payload.get("source_item_id"):
                _record_source_item_failure(
                    session,
                    source_item_id=str(job.payload["source_item_id"]),
                    job_type=str(job.type),
                    reason=job.last_error or "Background stage stopped before completion.",
                )
            if (
                job.status == JobStatus.FAILED.value
                and job.type == JobType.BUSINESS_INDEX_REFRESH.value
            ):
                _fail_expanding_campaigns(
                    session,
                    segment_id=str(job.payload["segment_id"]),
                    reason=job.last_error or "Background discovery stopped before completion.",
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
                JobType.SOURCE_ITEM_CLASSIFY.value: SourceItemStage.RELEVANCE,
                JobType.BUSINESS_IDENTITY_RESOLVE.value: SourceItemStage.IDENTITY,
                JobType.BUSINESS_OPPORTUNITY_AUDIT.value: SourceItemStage.OPPORTUNITY,
                JobType.SEARCH_ELIGIBILITY_MATCH.value: SourceItemStage.ELIGIBILITY,
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
    global _last_outcome_maintenance_date, _last_territory_scheduler_tick
    now = monotonic()
    if (
        services.settings.business_index_scheduler_enabled
        and now - _last_business_index_scheduler_tick >= 60
    ):
        enqueue_due_business_index_refreshes(session)
        _last_business_index_scheduler_tick = now
    if not services.settings.territory_scheduler_enabled:
        return
    if now - _last_territory_scheduler_tick < 60:
        return
    enqueue_due_territories(session)
    today = datetime.now(timezone.utc).date()
    if _last_outcome_maintenance_date != today:
        run_outcome_maintenance(
            session,
            no_response_days=services.settings.no_response_days,
        )
        _last_outcome_maintenance_date = today
    _last_territory_scheduler_tick = now


if __name__ == "__main__":
    run()
