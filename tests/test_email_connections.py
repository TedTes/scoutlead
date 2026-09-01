from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from db.session import create_database
from email_connections.crypto import TokenCipher
from email_connections.repository import EmailConnectionRepository
from email_connections.service import GmailOAuthService
from products.repository import ProductRepository
from products.schemas import DiscoverySource, DiscoverySourceType, ProductCreate, QualificationCriterion


def test_gmail_authorization_url_contains_send_scope_and_signed_product_state() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(_product_create())
        service = GmailOAuthService(session=session, settings=_settings())

        result = service.authorization_url(product.id)

        parsed = urlparse(result.authorization_url)
        params = parse_qs(parsed.query)
        assert parsed.netloc == "accounts.google.com"
        assert params["client_id"] == ["client-id"]
        assert params["access_type"] == ["offline"]
        assert params["prompt"] == ["consent"]
        scopes = params["scope"][0].split()
        assert scopes == ["openid", "email", "https://www.googleapis.com/auth/gmail.send"]
        assert service._decode_state(params["state"][0])["product_id"] == product.id


def test_gmail_oauth_callback_stores_encrypted_refresh_token(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    key = Fernet.generate_key().decode()

    class Response:
        status_code = 200
        text = "{}"

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_post(url: str, **kwargs):
        assert url == "https://oauth2.googleapis.com/token"
        assert kwargs["data"]["grant_type"] == "authorization_code"
        return Response(
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "scope": "openid email https://www.googleapis.com/auth/gmail.send",
                "id_token": _fake_id_token({"email": "founder@example.com"}),
            }
        )

    monkeypatch.setattr("email_connections.service.httpx.post", fake_post)

    with session_factory() as session:
        product = ProductRepository(session).create(_product_create())
        service = GmailOAuthService(session=session, settings=_settings(key=key))
        state = parse_qs(urlparse(service.authorization_url(product.id).authorization_url).query)["state"][0]

        connection = service.complete_oauth(code="oauth-code", state=state)

        stored = EmailConnectionRepository(session).get_active_for_product(product.id)
        assert connection.connected is True
        assert connection.email_address == "founder@example.com"
        assert stored is not None
        assert stored.encrypted_refresh_token != "refresh-token"
        assert TokenCipher(key).decrypt(stored.encrypted_refresh_token or "") == "refresh-token"


def test_gmail_disconnect_clears_stored_refresh_token() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    key = Fernet.generate_key().decode()

    with session_factory() as session:
        product = ProductRepository(session).create(_product_create())
        EmailConnectionRepository(session).upsert(
            product_id=product.id,
            provider="gmail",
            email_address="founder@example.com",
            encrypted_refresh_token=TokenCipher(key).encrypt("refresh-token"),
            scopes=["openid", "email", "https://www.googleapis.com/auth/gmail.send"],
        )

        status = GmailOAuthService(session=session, settings=_settings(key=key)).disconnect(product.id)

        stored = EmailConnectionRepository(session).get_for_product(product.id)
        assert status.connected is False
        assert stored is not None
        assert stored.disconnected_at is not None
        assert stored.encrypted_refresh_token is None


def _settings(key: str | None = None) -> Settings:
    return Settings(
        google_oauth_client_id="client-id",
        google_oauth_client_secret="client-secret",
        google_oauth_redirect_uri="http://localhost:8000/email/gmail/callback",
        google_oauth_state_secret="state-secret",
        google_token_encryption_key=key or Fernet.generate_key().decode(),
    )


def _product_create() -> ProductCreate:
    return ProductCreate(
        product_name="QuoteVan",
        product_description="Mobile quoting software for painters.",
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


def _fake_id_token(payload: dict) -> str:
    header = {"alg": "none"}
    return ".".join(
        [
            _urlsafe(json.dumps(header).encode()),
            _urlsafe(json.dumps(payload).encode()),
            "signature",
        ]
    )


def _urlsafe(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
