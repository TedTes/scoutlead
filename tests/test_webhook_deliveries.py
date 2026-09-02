from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, LeadSeedInput
from db.session import create_database
from leads.repository import LeadRepository
from leads.schemas import ContactVerificationStatus, LeadReviewStatus, LeadUpdate, LeadVerification
from messages.schemas import MessageApproval, OutreachDraft
from messages.service import MessageService
from products.repository import ProductRepository
from products.schemas import ProductUpdate
from tests.test_discovery_candidates import product_input
from tools.email import EmailTool
from webhooks.schemas import WebhookDeliveryCreate, WebhookDeliveryStatus
from webhooks.service import WebhookDeliveryService


class DraftLLM:
    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model,
        context: dict | None = None,
    ):
        del task, system, prompt, response_model, context
        return OutreachDraft(
            subject="QuoteVan question",
            body="Open to sharing how you handle quotes today?",
            personalization_notes=["Mentions residential painting."],
            approach_tag="manual_shortlist",
        )


def test_webhook_delivery_posts_approved_shortlist(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        status_code = 200
        text = "ok"

        def raise_for_status(self) -> None:
            return None

    def fake_post(*args, **kwargs):
        captured["url"] = args[0]
        captured["json"] = kwargs["json"]
        return Response()

    monkeypatch.setattr("webhooks.service.httpx.post", fake_post)

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product_repo = ProductRepository(session)
        product = product_repo.create(product_input())
        product_repo.update(
            product.id,
            ProductUpdate(webhook_url="https://hooks.example/approved", webhook_enabled=True),
        )
        campaign = CampaignRepository(session).create(
            CampaignCreate(product_id=product.id, name="Painters Toronto", max_leads=5)
        )
        lead_repo = LeadRepository(session)
        lead = lead_repo.create_from_seed(
            campaign.id,
            product.id,
            LeadSeedInput(
                company_name="Cedar & Sons Painting",
                website_url="https://cedarpaint.example",
                contact_email="owner@cedarpaint.example",
                geography="Toronto, ON",
                description="Residential painting company",
                raw={"phone": "(416) 555-0133"},
            ),
        )
        lead_repo.update(
            lead.id,
            LeadUpdate(review_status=LeadReviewStatus.GOOD_FIT, shortlisted=True),
        )
        lead_repo.attach_verification(
            lead.id,
            LeadVerification(
                status=ContactVerificationStatus.VALID,
                provider="syntax",
                reason="Email syntax is valid.",
                score=80,
            ),
        )
        message_service = MessageService(session=session, email=EmailTool(), llm=DraftLLM())
        message = message_service.create_outreach_draft_for_lead(lead.id)
        message_service.approve(message.id, MessageApproval(approved_by="operator"))

        delivery = WebhookDeliveryService(session).send_approved_shortlist(
            campaign.id,
            WebhookDeliveryCreate(),
        )

        payload = captured["json"]
        assert captured["url"] == "https://hooks.example/approved"
        assert delivery.status == WebhookDeliveryStatus.SUCCESS
        assert payload["event"] == "approved_shortlist.ready"
        assert payload["product"]["id"] == product.id
        assert payload["run"]["id"] == campaign.id
        assert payload["contacts"][0]["company_name"] == "Cedar & Sons Painting"
        assert payload["contacts"][0]["email"] == "owner@cedarpaint.example"
        assert payload["contacts"][0]["phone"] == "(416) 555-0133"
        assert payload["contacts"][0]["outreach"]["message_id"] == message.id


def test_webhook_url_requires_http_url() -> None:
    try:
        ProductUpdate(webhook_url="hooks.example/approved", webhook_enabled=True)
    except ValidationError as exc:
        assert "webhook_url must start with http:// or https://" in str(exc)
    else:
        raise AssertionError("invalid webhook URL was accepted")

    assert ProductUpdate(webhook_url="  https://hooks.example/approved  ").webhook_url == "https://hooks.example/approved"
