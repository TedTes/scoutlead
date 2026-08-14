from time import sleep

from agent_runs.repository import AgentRunRepository
from app.config import get_settings
from app.dependencies import create_app_services
from campaigns.service import CampaignService
from db.session import create_database
from messages.service import MessageService
from queue.repository import QueueRepository
from queue.schemas import JobType
from shared.logger import configure_logging, get_logger

logger = get_logger(__name__)


def run_once() -> bool:
    # Keep this entrypoint minimal for the Railway worker process.
    settings = get_settings()
    configure_logging(settings.log_level)
    services = create_app_services(settings)
    create_database(services.db.engine)

    generator = services.db.session()
    session = next(generator)
    try:
        agent_runs = AgentRunRepository(session)
        agent_run = agent_runs.claim_next()
        if agent_run is not None:
            try:
                CampaignService(
                    session=session,
                    llm=services.llm,
                    search_tool=services.search,
                    browser=services.browser,
                ).run_campaign(agent_run.campaign_id, agent_run_id=agent_run.id)
            except Exception:
                logger.exception("agent_run_failed run_id=%s", agent_run.id)
            return True

        queue = QueueRepository(session)
        job = queue.claim_next()
        if job is None:
            return False
        try:
            if job.type == JobType.CAMPAIGN_RUN.value:
                CampaignService(
                    session=session,
                    llm=services.llm,
                    search_tool=services.search,
                    browser=services.browser,
                ).run_campaign(str(job.payload["campaign_id"]))
            elif job.type == JobType.MESSAGE_SEND.value:
                MessageService(session=session, email=services.email).send(
                    str(job.payload["message_id"])
                )
            else:
                raise ValueError(f"unknown job type: {job.type}")
        except Exception as exc:
            logger.exception("job_failed job_id=%s", job.id)
            queue.fail(job.id, str(exc))
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
