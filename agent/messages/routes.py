from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import AppServices, CurrentAuth, DbSession, get_services
from campaigns.repository import CampaignRepository
from job_queue.schemas import QueueJobRead
from job_queue.service import QueueService
from messages.repository import MessageRepository
from messages.schemas import MessageApproval, MessageRead, MessageReplyMark, MessageUpdate
from messages.service import MessageService

router = APIRouter(tags=["messages"])


@router.get("/campaigns/{campaign_id}/messages", response_model=list[MessageRead])
def list_campaign_messages(campaign_id: str, session: DbSession, auth: CurrentAuth):
    CampaignRepository(session, workspace_id=auth.workspace_id).get(campaign_id)
    return MessageRepository(session, workspace_id=auth.workspace_id).list_by_campaign(campaign_id)


@router.get("/messages/{message_id}", response_model=MessageRead)
def get_message(message_id: str, session: DbSession, auth: CurrentAuth):
    return MessageRepository(session, workspace_id=auth.workspace_id).get(message_id)


@router.post("/leads/{lead_id}/outreach-draft", response_model=MessageRead)
def create_lead_outreach_draft(
    lead_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return MessageService(
        session=session,
        email=services.email,
        llm=services.llm,
        workspace_id=auth.workspace_id,
    ).create_outreach_draft_for_lead(lead_id)


@router.patch("/messages/{message_id}", response_model=MessageRead)
def update_message(
    message_id: str,
    update: MessageUpdate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return MessageService(session=session, email=services.email, workspace_id=auth.workspace_id).update(
        message_id,
        update,
    )


@router.post("/messages/{message_id}/approve", response_model=MessageRead)
def approve_message(
    message_id: str,
    approval: MessageApproval,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return MessageService(session=session, email=services.email, workspace_id=auth.workspace_id).approve(
        message_id,
        approval,
    )


@router.post("/messages/{message_id}/send", response_model=MessageRead)
def send_message(
    message_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return MessageService(session=session, email=services.email, workspace_id=auth.workspace_id).send(message_id)


@router.post("/messages/{message_id}/cancel", response_model=MessageRead)
def cancel_message(
    message_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return MessageService(session=session, email=services.email, workspace_id=auth.workspace_id).cancel(message_id)


@router.post("/messages/{message_id}/mark-replied", response_model=MessageRead)
def mark_message_replied(
    message_id: str,
    reply: MessageReplyMark,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return MessageService(
        session=session,
        email=services.email,
        workspace_id=auth.workspace_id,
    ).mark_replied(message_id, reply)


@router.post("/messages/{message_id}/enqueue-send", response_model=QueueJobRead)
def enqueue_send_message(message_id: str, session: DbSession, auth: CurrentAuth):
    MessageRepository(session, workspace_id=auth.workspace_id).get(message_id)
    return QueueService(session).enqueue_message_send(message_id)
