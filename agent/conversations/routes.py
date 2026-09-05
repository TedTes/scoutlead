from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import AppServices, CurrentAuth, DbSession, get_services
from campaigns.repository import CampaignRepository
from db.models import ConversationModel
from shared.errors import NotFoundError
from conversations.schemas import ConversationRead, InboundResponseCreate, ManualClassificationCreate
from conversations.service import ConversationService

router = APIRouter(tags=["conversations"])


@router.get("/campaigns/{campaign_id}/conversations", response_model=list[ConversationRead])
def list_campaign_conversations(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    CampaignRepository(session, workspace_id=auth.workspace_id).get(campaign_id)
    return ConversationService(
        session=session,
        llm=services.llm,
        workspace_id=auth.workspace_id,
    ).list_by_campaign(campaign_id)


@router.post("/conversations/{conversation_id}/responses", response_model=ConversationRead)
def record_response(
    conversation_id: str,
    inbound: InboundResponseCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _assert_conversation_in_scope(conversation_id, session, auth)
    return ConversationService(
        session=session,
        llm=services.llm,
        workspace_id=auth.workspace_id,
    ).classify_response(
        conversation_id, inbound.body
    )


@router.post("/conversations/{conversation_id}/classification", response_model=ConversationRead)
def manually_classify_response(
    conversation_id: str,
    classification: ManualClassificationCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _assert_conversation_in_scope(conversation_id, session, auth)
    return ConversationService(
        session=session,
        llm=services.llm,
        workspace_id=auth.workspace_id,
    ).manually_classify(
        conversation_id, classification
    )


def _assert_conversation_in_scope(conversation_id: str, session: DbSession, auth: CurrentAuth) -> None:
    conversation = session.get(ConversationModel, conversation_id)
    if conversation is None:
        raise NotFoundError("conversation not found", {"conversation_id": conversation_id})
    CampaignRepository(session, workspace_id=auth.workspace_id).get(conversation.campaign_id)
