from fastapi import APIRouter

from app.config import get_settings
from connections.schemas import ConnectionStatus

router = APIRouter(prefix="/connections", tags=["connections"])


@router.get("/status", response_model=list[ConnectionStatus])
def list_connection_status() -> list[ConnectionStatus]:
    settings = get_settings()
    strict = settings.strict_external_providers
    search_ready = bool(settings.search_api_key or settings.search_api_endpoint)
    llm_ready = bool(settings.openai_api_key or settings.llm_json_endpoint)
    email_ready = (
        bool(settings.email_provider_endpoint)
        if settings.email_provider == "http"
        else bool(settings.resend_api_key and settings.email_from_address)
        if settings.email_provider == "resend"
        else not strict and not settings.require_real_email
    )
    return [
        ConnectionStatus(
            name="Database",
            category="persistence",
            status="connected" if settings.database_url else "not_configured",
            detail="Campaign state and outcomes",
        ),
        ConnectionStatus(
            name="LLM provider",
            category="reasoning",
            status="connected" if llm_ready else "not_configured",
            detail=settings.openai_model if settings.openai_api_key else "Remote JSON LLM" if settings.llm_json_endpoint else "LLM required",
        ),
        ConnectionStatus(
            name="Search provider",
            category="discovery",
            status="connected" if search_ready else "not_configured" if strict else "degraded",
            detail=settings.search_provider,
        ),
        ConnectionStatus(
            name="Email provider",
            category="outreach",
            status="connected" if email_ready else "not_configured",
            detail=settings.email_provider,
        ),
    ]
