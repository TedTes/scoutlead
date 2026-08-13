from fastapi import APIRouter

from app.config import get_settings
from connections.schemas import ConnectionStatus

router = APIRouter(prefix="/connections", tags=["connections"])


@router.get("/status", response_model=list[ConnectionStatus])
def list_connection_status() -> list[ConnectionStatus]:
    settings = get_settings()
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
            status="connected" if settings.openai_api_key or settings.llm_api_key else "not_configured",
            detail=settings.openai_model if settings.openai_api_key else "Heuristic fallback",
        ),
        ConnectionStatus(
            name="Search provider",
            category="discovery",
            status="connected" if settings.search_api_key or settings.search_api_endpoint else "not_configured",
            detail=settings.search_provider,
        ),
        ConnectionStatus(
            name="Email provider",
            category="outreach",
            status="connected" if settings.email_api_key or settings.email_provider_endpoint else "not_configured",
            detail="Outbound send tool",
        ),
    ]
