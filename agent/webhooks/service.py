from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead
from db.models import WebhookDeliveryModel
from leads.repository import LeadRepository
from leads.schemas import LeadRead
from messages.repository import MessageRepository
from messages.schemas import MessageRead, MessageStatus
from products.repository import ProductRepository
from products.schemas import ProductRead
from shared.errors import ConfigurationError, ConflictError
from shared.utils import new_id, truncate
from webhooks.schemas import WebhookDeliveryCreate, WebhookDeliveryRead, WebhookDeliveryStatus


class WebhookDeliveryService:
    def __init__(self, session: Session, *, timeout_seconds: float = 20.0) -> None:
        self.session = session
        self.timeout_seconds = timeout_seconds
        self.campaigns = CampaignRepository(session)
        self.products = ProductRepository(session)
        self.leads = LeadRepository(session)
        self.messages = MessageRepository(session)

    def list_by_campaign(self, campaign_id: str) -> list[WebhookDeliveryRead]:
        self.campaigns.get(campaign_id)
        statement = (
            select(WebhookDeliveryModel)
            .where(WebhookDeliveryModel.campaign_id == campaign_id)
            .order_by(WebhookDeliveryModel.created_at.desc())
        )
        return [WebhookDeliveryRead.model_validate(model) for model in self.session.scalars(statement)]

    def send_approved_shortlist(
        self,
        campaign_id: str,
        request: WebhookDeliveryCreate,
    ) -> WebhookDeliveryRead:
        campaign = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        product = ProductRead.model_validate(self.products.get(campaign.product_id))
        if not product.webhook_enabled or not product.webhook_url:
            raise ConfigurationError(
                "product webhook is not configured",
                {
                    "product_id": product.id,
                    "user_message": "Add and enable a webhook URL in product settings before sending.",
                },
            )

        payload = self._payload(product, campaign, request.event)
        if not payload["contacts"]:
            raise ConflictError(
                "approved shortlist is empty",
                {
                    "campaign_id": campaign.id,
                    "user_message": "Approve at least one shortlisted contact before sending the webhook.",
                },
            )

        response_status: int | None = None
        response_body: str | None = None
        error: str | None = None
        status = WebhookDeliveryStatus.SUCCESS
        try:
            response = httpx.post(
                product.webhook_url,
                headers={"content-type": "application/json", "user-agent": "scoutlead-webhook/0.1"},
                json=payload,
                timeout=self.timeout_seconds,
            )
            response_status = response.status_code
            response_body = truncate(response.text, 1000)
            response.raise_for_status()
        except Exception as exc:
            status = WebhookDeliveryStatus.FAILED
            error = str(exc)

        model = WebhookDeliveryModel(
            id=new_id("webhook_delivery"),
            product_id=product.id,
            campaign_id=campaign.id,
            event=request.event,
            url=product.webhook_url,
            status=status.value,
            request_payload=payload,
            response_status=response_status,
            response_body=response_body,
            error=error,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)

        if status == WebhookDeliveryStatus.FAILED:
            raise ConfigurationError(
                "webhook delivery failed",
                {
                    "delivery_id": model.id,
                    "status_code": response_status,
                    "response_body": response_body,
                    "error": error,
                    "user_message": "The webhook endpoint did not accept the approved shortlist.",
                },
            )

        return WebhookDeliveryRead.model_validate(model)

    def _payload(self, product: ProductRead, campaign: CampaignRead, event: str) -> dict[str, Any]:
        messages = [
            MessageRead.model_validate(message)
            for message in self.messages.list_by_campaign(campaign.id)
            if MessageStatus(message.status) in {MessageStatus.APPROVED, MessageStatus.SENT, MessageStatus.REPLIED}
        ]
        message_by_lead_id = {message.lead_id: message for message in messages}
        contacts = []
        for lead_model in self.leads.list_by_campaign(campaign.id):
            lead = LeadRead.model_validate(lead_model)
            message = message_by_lead_id.get(lead.id)
            if not lead.shortlisted_at or message is None:
                continue
            contacts.append(_contact_payload(lead, message))

        return {
            "event": event,
            "product": {
                "id": product.id,
                "name": product.product_name,
                "target_customer": product.target_customer,
                "target_geography": product.target_geography,
            },
            "run": {
                "id": campaign.id,
                "name": campaign.name,
                "goal_type": campaign.goal_type,
                "status": campaign.status,
            },
            "contacts": contacts,
        }


def _contact_payload(lead: LeadRead, message: MessageRead) -> dict[str, Any]:
    return {
        "id": lead.id,
        "company_name": lead.company_name,
        "website_url": lead.website_url or (lead.research.website_url if lead.research else None),
        "email": lead.contact_email or (lead.research.contact_email if lead.research else None),
        "phone": _lead_phone(lead),
        "geography": lead.geography or (lead.research.geography if lead.research else None),
        "contact_policy_status": lead.contact_policy_status.value,
        "verification": {
            "status": lead.verification_status.value,
            "provider": lead.verification_provider,
            "score": lead.verification_score,
            "reason": lead.verification_reason,
            "details": lead.verification_details or {},
        },
        "fit": {
            "review_status": lead.review_status.value,
            "score": lead.qualification.score if lead.qualification else None,
            "rationale": lead.qualification.rationale if lead.qualification else None,
            "positive_signals": lead.qualification.positive_signals if lead.qualification else [],
            "missing_evidence": lead.qualification.missing_evidence if lead.qualification else [],
        },
        "outreach": {
            "message_id": message.id,
            "status": message.status.value,
            "subject": message.subject,
            "body": message.body,
            "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        },
    }


def _lead_phone(lead: LeadRead) -> str | None:
    phone_keys = {
        "normalized_contact_phone",
        "contact_phone",
        "nationalPhoneNumber",
        "internationalPhoneNumber",
        "phone",
        "phoneNumber",
        "phone_number",
        "telephone",
        "contactPhone",
        "sellerPhone",
        "ownerPhone",
    }
    for raw in lead.raw_sources:
        value = _phone_from_raw(raw, phone_keys)
        if value:
            return value
        nested = raw.get("raw") if isinstance(raw, dict) else None
        if isinstance(nested, dict):
            value = _phone_from_raw(nested, phone_keys)
            if value:
                return value
    return None


def _phone_from_raw(raw: dict, phone_keys: set[str]) -> str | None:
    for key in phone_keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return None
