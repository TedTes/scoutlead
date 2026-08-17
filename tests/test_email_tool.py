from datetime import datetime, timezone

from leads.schemas import LeadRead
from messages.schemas import MessageRead, MessageStatus
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
