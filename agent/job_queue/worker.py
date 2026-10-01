from datetime import date, datetime, time, timezone
from time import monotonic, sleep

from sqlalchemy.orm import Session

from agent_runs.repository import AgentRunRepository
from app.config import get_settings
from app.dependencies import AppServices, create_app_services
from app.service_factory import (
    business_index_refresh_service,
    campaign_service,
    territory_refresh_service,
)
from business_index.scheduler import enqueue_due_business_index_refreshes
from campaigns.service import CampaignService
from db.session import create_database
from db.models import TerritoryModel
from job_queue.repository import QueueRepository
from job_queue.schemas import JobType
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
                business_index_refresh_service(
                    session=session,
                    services=services,
                ).refresh(str(job.payload["segment_id"]))
            else:
                raise ValueError(f"unknown job type: {job.type}")
        except Exception as exc:
            logger.exception("job_failed job_id=%s", job.id)
            queue.fail(
                job.id,
                str(exc),
                retry_delay_seconds=(3600 if job.type == JobType.TERRITORY_REFRESH.value else None),
            )
            return True
        queue.complete(job.id)
        return True
    finally:
        generator.close()


def run() -> None:
    while True:
        did_work = run_once()
        if not did_work:
            sleep(2)


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
