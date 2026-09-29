import base64
from datetime import datetime, timezone
from email import message_from_bytes
from email.header import decode_header, make_header

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, LeadSeedInput
from db.models import WorkspaceModel
from db.session import create_database
from leads.repository import LeadRepository
from leads.schemas import ContactPolicyStatus, LeadRead
from messages.schemas import MessageRead, MessageStatus
from products.repository import ProductRepository
from products.schemas import ProductCreate, ProductRead, QualificationCriterion
from shared.errors import ValidationError
from tools.email import EmailTool
from unsubscribe.service import UnsubscribeService
from unsubscribe.tokens import (
    UnsubscribeClaims,
    sign_unsubscribe_token,
    verify_unsubscribe_token,
)


def test_unsubscribe_token_rejects_tampering() -> None:
    token = sign_unsubscribe_token(
        UnsubscribeClaims(
            workspace_id="workspace:first",
            lead_id="lead:first",
            email="owner@example.test",
        ),
        "test-secret",
    )

    assert verify_unsubscribe_token(token, "test-secret").lead_id == "lead:first"
    with pytest.raises(ValidationError):
        verify_unsubscribe_token(f"{token[:-1]}x", "test-secret")


def test_unsubscribe_blocks_same_contact_across_workspace_offers() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        first_product, first_campaign = _offer_and_campaign(
            session, workspace_id="workspace:first", name="Coverage"
        )
        lead = _lead(
            session,
            product=first_product,
            campaign=first_campaign,
            email="owner@example.test",
        )
        token = sign_unsubscribe_token(
            UnsubscribeClaims(
                workspace_id="workspace:first",
                lead_id=lead.id,
                email="owner@example.test",
            ),
            "test-secret",
        )

        UnsubscribeService(session, signing_secret="test-secret").unsubscribe(token)

        second_product, second_campaign = _offer_and_campaign(
            session, workspace_id="workspace:first", name="Fleet cards"
        )
        rediscovered = _lead(
            session,
            product=second_product,
            campaign=second_campaign,
            email="owner@example.test",
        )
        assert rediscovered.contact_policy_status == ContactPolicyStatus.UNSUBSCRIBED.value

        other_product, other_campaign = _offer_and_campaign(
            session, workspace_id="workspace:other", name="Bookkeeping"
        )
        other_workspace = _lead(
            session,
            product=other_product,
            campaign=other_campaign,
            email="owner@example.test",
        )
        assert other_workspace.contact_policy_status == ContactPolicyStatus.ALLOWED.value


def test_compliant_resend_and_gmail_content_contains_footer_and_headers(monkeypatch) -> None:
    session_factory = _session_factory()
    captured: dict = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"id": "email_123"}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("tools.email.httpx.post", fake_post)
    with session_factory() as session:
        product, campaign = _offer_and_campaign(
            session, workspace_id="workspace:first", name="Coverage"
        )
        workspace = session.get(WorkspaceModel, "workspace:first")
        workspace.sender_legal_name = "Example Brokerage Inc."
        workspace.sender_mailing_address = "100 King Street, Toronto, ON"
        workspace.sender_contact = "compliance@example.test"
        lead_model = _lead(
            session,
            product=product,
            campaign=campaign,
            email="owner@example.test",
        )
        session.commit()
        lead = LeadRead.model_validate(lead_model)
        message = _message(product.id, campaign.id, lead.id)
        tool = EmailTool(
            provider="resend",
            resend_api_key="re_test",
            from_address="sender@example.test",
            compliance_enabled=True,
            unsubscribe_signing_secret="test-secret",
            public_api_base="https://api.example.test",
        ).bind_session(session)

        tool.send(
            product=ProductRead.model_validate(product),
            lead=lead,
            message=message,
        )

        resend_payload = captured["json"]
        assert "Example Brokerage Inc." in resend_payload["text"]
        assert "Unsubscribe: https://api.example.test/u/" in resend_payload["text"]
        unsubscribe_header = resend_payload["headers"]["List-Unsubscribe"]
        assert unsubscribe_header.startswith("<https://api.example.test/u/")

        body, unsubscribe_url = tool._delivery_content(
            product=ProductRead.model_validate(product),
            lead=lead,
            message=message,
        )
        mime = tool._build_gmail_message(
            from_address="sender@example.test",
            to_address=lead.contact_email,
            subject=message.subject or "Question",
            body=body,
            message_id=message.id,
            unsubscribe_url=unsubscribe_url,
        )
        decoded = message_from_bytes(base64.urlsafe_b64decode(base64.urlsafe_b64encode(mime.as_bytes())))
        unsubscribe_value = str(make_header(decode_header(decoded["List-Unsubscribe"])))
        assert unsubscribe_value == f"<{unsubscribe_url}>"
        assert decoded["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert "100 King Street" in decoded.get_payload()


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _offer_and_campaign(session, *, workspace_id: str, name: str):
    product = ProductRepository(session, workspace_id=workspace_id).create(
        ProductCreate(
            product_name=name,
            offer_summary=f"{name} for contractors.",
            target_customer="HVAC contractors",
            target_geography="Toronto",
            qualification_criteria=[QualificationCriterion(label="HVAC business")],
        )
    )
    campaign = CampaignRepository(session, workspace_id=workspace_id).create(
        CampaignCreate(product_id=product.id, name=f"{name} Toronto", max_leads=25)
    )
    return product, campaign


def _lead(session, *, product, campaign, email: str):
    return LeadRepository(session).create_from_seed(
        campaign.id,
        product.id,
        LeadSeedInput(
            company_name="Example HVAC",
            website_url="https://example-hvac.test",
            contact_email=email,
            geography="Toronto",
            description="HVAC contractor",
        ),
    )


def _message(product_id: str, campaign_id: str, lead_id: str) -> MessageRead:
    now = datetime.now(timezone.utc)
    return MessageRead(
        id="message:first",
        campaign_id=campaign_id,
        product_id=product_id,
        lead_id=lead_id,
        subject="Quick question",
        body="Hello, is this relevant?",
        status=MessageStatus.APPROVED,
        created_at=now,
        updated_at=now,
    )
