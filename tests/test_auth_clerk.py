from app.config import Settings
from auth.clerk import ClerkTokenVerifier


def test_clerk_verifier_derives_issuer_when_issuer_env_is_jwks_url() -> None:
    verifier = ClerkTokenVerifier(
        Settings(
            _env_file=None,
            clerk_jwt_issuer="https://modest-turkey-522.clerk.accounts.dev/.well-known/jwks.json",
        )
    )

    assert verifier.issuer == "https://modest-turkey-522.clerk.accounts.dev"
    assert verifier.jwks_url == (
        "https://modest-turkey-522.clerk.accounts.dev/.well-known/jwks.json"
    )


def test_clerk_verifier_deduplicates_explicit_jwks_url() -> None:
    verifier = ClerkTokenVerifier(
        Settings(
            _env_file=None,
            clerk_jwks_url=(
                "https://modest-turkey-522.clerk.accounts.dev/.well-known/jwks.json"
                "/.well-known/jwks.json"
            ),
        )
    )

    assert verifier.jwks_url == (
        "https://modest-turkey-522.clerk.accounts.dev/.well-known/jwks.json"
    )
