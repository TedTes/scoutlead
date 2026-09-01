from datetime import datetime, timezone
from email import message_from_bytes
import base64

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.session import create_database
from email_connections.crypto import TokenCipher
from email_connections.repository import EmailConnectionRepository
from leads.schemas import LeadRead
from messages.schemas import MessageRead, MessageStatus
from products.repository import ProductRepository
from products.schemas import DiscoverySource, DiscoverySourceType, ProductRead, QualificationCriterion
from tools.email import EmailTool


def test_resend_email_provider_posts_traceable_payload(monkeypatch) -> None:
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
    now = datetime.now(timezone.utc)
    product = ProductRead(
        id="product_123",
        product_name="Loop",
        product_description="Async standups",
        target_customer="Remote teams",
        problem_being_solved="Meeting fatigue",
        value_proposition="Async blockers",
        target_geography="North America",
        validation_goal="Book interviews",
        qualification_criteria=[QualificationCriterion(label="Remote engineering team")],
        preferred_discovery_sources=[
            DiscoverySource(type=DiscoverySourceType.WEB_SEARCH, value="remote engineering teams")
        ],
        outreach_objective="Ask for a call",
        constraints=[],
        archived_at=None,
        created_at=now,
        updated_at=now,
    )
    lead = LeadRead(
        id="lead_123",
        campaign_id="campaign_123",
        product_id=product.id,
        company_name="Fernwood Labs",
        website_url="https://fernwood.example",
        contact_email="founder@fernwood.example",
        geography="North America",
        description="Remote engineering team",
        source="search",
        raw_sources=[],
        status="awaiting_approval",
        research=None,
        qualification=None,
        created_at=now,
        updated_at=now,
    )
    message = MessageRead(
        id="message_123",
        campaign_id="campaign_123",
        product_id=product.id,
        lead_id=lead.id,
        channel="email",
        subject="Loop question",
        body="Open to a short discovery call?",
        personalization_notes=[],
        approach_tag="concise_validation_request",
        status=MessageStatus.APPROVED,
        approval={"approved_by": "tedros"},
        sent_at=None,
        provider_message_id=None,
        failure_reason=None,
        created_at=now,
        updated_at=now,
    )

    result = EmailTool(
        provider="resend",
        resend_api_key="re_test",
        from_address="founder@example.com",
        from_name="ScoutLead",
        reply_to="reply@example.com",
    ).send(product=product, lead=lead, message=message)

    assert result.provider_message_id == "resend:email_123"
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["authorization"] == "Bearer re_test"
    assert captured["headers"]["Idempotency-Key"] == message.id
    assert captured["json"]["from"] == "ScoutLead <founder@example.com>"
    assert captured["json"]["to"] == [lead.contact_email]
    assert captured["json"]["reply_to"] == "reply@example.com"
    assert captured["json"]["subject"] == "Loop question"
    assert captured["json"]["text"] == message.body
    assert {"name": "message_id", "value": message.id} in captured["json"]["tags"]


def test_gmail_email_provider_refreshes_token_and_sends_mime_message(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    captured: dict = {}
    key = Fernet.generate_key().decode()

    class Response:
        def __init__(self, payload: dict, status_code: int = 200) -> None:
            self.payload = payload
            self.status_code = status_code
            self.text = str(payload)

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_post(url: str, **kwargs):
        if url == "https://oauth2.googleapis.com/token":
            captured["token_request"] = kwargs
            return Response({"access_token": "access-token"})
        captured["send_url"] = url
        captured["send_request"] = kwargs
        return Response({"id": "gmail-message-123", "threadId": "thread-123"})

    monkeypatch.setattr("tools.email.httpx.post", fake_post)

    with session_factory() as session:
        product = ProductRepository(session).create(
            _product_create(
                product_name="QuoteVan",
                product_description="Mobile quoting software for painters.",
            )
        )
        EmailConnectionRepository(session).upsert(
            product_id=product.id,
            provider="gmail",
            email_address="founder@example.com",
            encrypted_refresh_token=TokenCipher(key).encrypt("refresh-token"),
            scopes=["openid", "email", "https://www.googleapis.com/auth/gmail.send"],
        )

        now = datetime.now(timezone.utc)
        lead = LeadRead(
            id="lead_123",
            campaign_id="campaign_123",
            product_id=product.id,
            company_name="Toronto Painters",
            website_url="https://torontopainters.example",
            contact_email="owner@torontopainters.example",
            geography="Toronto",
            description="Painting contractor",
            source="search",
            raw_sources=[],
            status="awaiting_approval",
            created_at=now,
            updated_at=now,
        )
        message = MessageRead(
            id="message_123",
            campaign_id="campaign_123",
            product_id=product.id,
            lead_id=lead.id,
            channel="email",
            subject="QuoteVan question",
            body="Hi there,\n\nOpen to a quick question?",
            personalization_notes=[],
            approach_tag="concise_validation_request",
            status=MessageStatus.APPROVED,
            approval={"approved_by": "operator"},
            sent_at=None,
            provider_message_id=None,
            failure_reason=None,
            created_at=now,
            updated_at=now,
        )

        result = EmailTool(
            provider="gmail",
            from_name="ScoutLead",
            google_oauth_client_id="client-id",
            google_oauth_client_secret="client-secret",
            google_token_encryption_key=key,
        ).bind_session(session).send(
            product=ProductRead.model_validate(product),
            lead=lead,
            message=message,
        )

    assert result.provider_message_id == "gmail:gmail-message-123"
    assert captured["token_request"]["data"]["refresh_token"] == "refresh-token"
    assert captured["send_url"] == "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    assert captured["send_request"]["headers"]["authorization"] == "Bearer access-token"
    raw = captured["send_request"]["json"]["raw"]
    decoded = base64.urlsafe_b64decode(raw.encode())
    mime = message_from_bytes(decoded)
    assert mime["To"] == "owner@torontopainters.example"
    assert mime["From"] == "ScoutLead <founder@example.com>"
    assert mime["Subject"] == "QuoteVan question"
    assert mime["X-ScoutLead-Message-Id"] == message.id


def _product_create(product_name: str, product_description: str):
    from products.schemas import ProductCreate

    return ProductCreate(
        product_name=product_name,
        product_description=product_description,
        target_customer="Residential painters",
        problem_being_solved="Quotes are slow.",
        value_proposition="Create faster quote packages.",
        target_geography="Toronto ON",
        validation_goal="Find painters to validate the product.",
        qualification_criteria=[QualificationCriterion(label="Residential painting business")],
        preferred_discovery_sources=[
            DiscoverySource(type=DiscoverySourceType.WEB_SEARCH, value="painters Toronto")
        ],
        outreach_objective="Ask for a short product conversation.",
        constraints=[],
    )
