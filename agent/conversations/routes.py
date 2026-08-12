from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import AppServices, DbSession, get_services
from conversations.schemas import ConversationRead, InboundResponseCreate
from conversations.service import ConversationService

router = APIRouter(tags=["conversations"])


@router.get("/campaigns/{campaign_id}/conversations", response_model=list[ConversationRead])
def list_campaign_conversations(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return ConversationService(session=session, llm=services.llm).list_by_campaign(campaign_id)


@router.post("/conversations/{conversation_id}/responses", response_model=ConversationRead)
def record_response(
    conversation_id: str,
    inbound: InboundResponseCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return ConversationService(session=session, llm=services.llm).classify_response(
        conversation_id, inbound.body
    )
