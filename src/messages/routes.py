from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import AppServices, DbSession, get_services
from messages.repository import MessageRepository
from messages.schemas import MessageApproval, MessageRead
from messages.service import MessageService
from queue.schemas import QueueJobRead
from queue.service import QueueService

router = APIRouter(tags=["messages"])


@router.get("/campaigns/{campaign_id}/messages", response_model=list[MessageRead])
def list_campaign_messages(campaign_id: str, session: DbSession):
    return MessageRepository(session).list_by_campaign(campaign_id)


@router.get("/messages/{message_id}", response_model=MessageRead)
def get_message(message_id: str, session: DbSession):
    return MessageRepository(session).get(message_id)


@router.post("/messages/{message_id}/approve", response_model=MessageRead)
def approve_message(
    message_id: str,
    approval: MessageApproval,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return MessageService(session=session, email=services.email).approve(message_id, approval)


@router.post("/messages/{message_id}/send", response_model=MessageRead)
def send_message(
    message_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return MessageService(session=session, email=services.email).send(message_id)


@router.post("/messages/{message_id}/enqueue-send", response_model=QueueJobRead)
def enqueue_send_message(message_id: str, session: DbSession):
    return QueueService(session).enqueue_message_send(message_id)
