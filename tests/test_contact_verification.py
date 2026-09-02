from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import pytest

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, LeadSeedInput
from campaigns.service import CampaignService
from db.session import create_database
from leads.policy import is_verified_lead
from leads.repository import LeadRepository
from leads.schemas import ContactVerificationStatus, LeadRead, LeadVerification
from products.repository import ProductRepository
from tests.test_discovery_candidates import product_input
from tests.test_smoke_campaign import FakeWorkflowLLM
from tools.browser import DirectHttpBrowserTool
from tools.search import SearchTool
from tools.verify import EmailVerificationTool


def test_invalid_email_syntax_is_not_verified() -> None:
    result = EmailVerificationTool().run({"email": "not-an-email"})

    assert result.data["status"] == "invalid"
    assert result.confidence == 20


def test_risky_provider_result_does_not_count_as_verified(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"status": "risky", "score": 55, "reason": "Mailbox accepts all domains."}

    def fake_post(*args, **kwargs):
        return Response()

    monkeypatch.setattr("tools.verify.httpx.post", fake_post)
    result = EmailVerificationTool(
        provider="http",
        endpoint="https://verifier.example/check",
        api_key="test_key",
    ).run({"email": "owner@example.com"})

    assert result.data["status"] == "risky"
    assert result.confidence == 55


def test_bouncer_provider_maps_deliverable_response(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "email": "owner@example.com",
                "status": "deliverable",
                "reason": "accepted_email",
                "score": 98,
                "acceptAll": False,
                "disposable": False,
                "role": False,
                "domain": "example.com",
            }

    def fake_get(*args, **kwargs):
        captured["url"] = args[0]
        captured["headers"] = kwargs["headers"]
        captured["params"] = kwargs["params"]
        return Response()

    monkeypatch.setattr("tools.verify.httpx.get", fake_get)

    result = EmailVerificationTool(
        provider="bouncer",
        bouncer_api_key="bouncer_test_key",
    ).run({"email": "owner@example.com"})

    assert captured["url"] == "https://api.usebouncer.com/v1.1/email/verify"
    assert captured["headers"] == {"x-api-key": "bouncer_test_key"}
    assert captured["params"] == {"email": "owner@example.com", "timeout": 20}
    assert result.provider == "bouncer"
    assert result.data["status"] == "valid"
    assert result.data["details"] == {
        "provider": "bouncer",
        "provider_status": "deliverable",
        "provider_reason": "accepted_email",
        "score": 98,
        "domain": "example.com",
        "disposable": False,
        "role": False,
        "accept_all": False,
    }
    assert result.confidence == 98


@pytest.mark.parametrize(
    ("provider_status", "expected_status", "expected_max_score"),
    [
        ("risky", "risky", 55),
        ("undeliverable", "invalid", 10),
        ("unknown", "unknown", 30),
    ],
)
def test_bouncer_provider_maps_non_verified_statuses(
    monkeypatch,
    provider_status: str,
    expected_status: str,
    expected_max_score: int,
) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "email": "owner@example.com",
                "status": provider_status,
                "reason": "mailbox_full" if provider_status == "risky" else "rejected_email",
            }

    monkeypatch.setattr("tools.verify.httpx.get", lambda *args, **kwargs: Response())

    result = EmailVerificationTool(
        provider="bouncer",
        bouncer_api_key="bouncer_test_key",
    ).run({"email": "owner@example.com"})

    assert result.provider == "bouncer"
    assert result.data["status"] == expected_status
    assert result.confidence <= expected_max_score


def test_bouncer_provider_requires_api_key() -> None:
    with pytest.raises(ValueError, match="BOUNCER_API_KEY"):
        EmailVerificationTool(provider="bouncer").run({"email": "owner@example.com"})


def test_bouncer_preflight_requires_api_key() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        service = CampaignService(
            session=session,
            llm=FakeWorkflowLLM(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            contact_verification_provider="bouncer",
        )

        assert service._contact_verification_check() == (
            "failed",
            "Configure BOUNCER_API_KEY for Bouncer contact verification.",
            True,
        )


def test_zerobounce_provider_maps_valid_response(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "address": "owner@example.com",
                "status": "valid",
                "sub_status": "",
                "quality_score": "0.98",
            }

    def fake_get(*args, **kwargs):
        captured["url"] = args[0]
        captured["params"] = kwargs["params"]
        return Response()

    monkeypatch.setattr("tools.verify.httpx.get", fake_get)

    result = EmailVerificationTool(
        provider="zerobounce",
        zerobounce_api_key="zb_test_key",
    ).run({"email": "owner@example.com"})

    assert captured["url"] == "https://api.zerobounce.net/v2/validate"
    assert captured["params"] == {"api_key": "zb_test_key", "email": "owner@example.com"}
    assert result.provider == "zerobounce"
    assert result.data["status"] == "valid"
    assert result.confidence == 98


@pytest.mark.parametrize(
    ("provider_status", "expected_status", "expected_max_score"),
    [
        ("catch-all", "risky", 55),
        ("do_not_mail", "invalid", 10),
        ("unknown", "unknown", 30),
    ],
)
def test_zerobounce_provider_maps_non_verified_statuses(
    monkeypatch,
    provider_status: str,
    expected_status: str,
    expected_max_score: int,
) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "address": "owner@example.com",
                "status": provider_status,
                "sub_status": "mail_server_temporary_error" if provider_status == "unknown" else "",
            }

    monkeypatch.setattr("tools.verify.httpx.get", lambda *args, **kwargs: Response())

    result = EmailVerificationTool(
        provider="zerobounce",
        zerobounce_api_key="zb_test_key",
    ).run({"email": "owner@example.com"})

    assert result.provider == "zerobounce"
    assert result.data["status"] == expected_status
    assert result.confidence <= expected_max_score


def test_zerobounce_provider_requires_api_key() -> None:
    with pytest.raises(ValueError, match="ZEROBOUNCE_API_KEY"):
        EmailVerificationTool(provider="zerobounce").run({"email": "owner@example.com"})


def test_zerobounce_preflight_requires_api_key() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        service = CampaignService(
            session=session,
            llm=FakeWorkflowLLM(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            contact_verification_provider="zerobounce",
        )

        assert service._contact_verification_check() == (
            "failed",
            "Configure ZEROBOUNCE_API_KEY for ZeroBounce contact verification.",
            True,
        )


def test_verified_status_is_persisted_on_lead() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(product_input())
        campaign = CampaignRepository(session).create(
            CampaignCreate(product_id=product.id, name="Painters Toronto", max_leads=5)
        )
        lead = LeadRepository(session).create_from_seed(
            campaign.id,
            product.id,
            LeadSeedInput(
                company_name="Cedar & Sons Painting",
                website_url="https://cedarpaint.example",
                contact_email="owner@cedarpaint.example",
                geography="Toronto, ON",
                description="Residential painting company",
            ),
        )
        result = EmailVerificationTool().run({"email": lead.contact_email})
        updated = LeadRepository(session).attach_verification(
            lead.id,
            LeadVerification(
                status=result.data["status"],
                provider=result.provider,
                reason=result.data["reason"],
                score=result.data["score"],
            ),
        )

        read = LeadRead.model_validate(updated)
        assert read.verification_status == ContactVerificationStatus.VALID
        assert read.verification_provider == "syntax"
        assert read.verification_checked_at is not None
        assert is_verified_lead(read)
