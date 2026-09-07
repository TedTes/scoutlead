from app.config import Settings
from auth.clerk import AuthError, ClerkTokenVerifier, _split_token


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


def test_clerk_verifier_strips_repeated_jwks_path_from_issuer() -> None:
    verifier = ClerkTokenVerifier(
        Settings(
            _env_file=None,
            clerk_jwt_issuer=(
                "https://modest-turkey-522.clerk.accounts.dev/.well-known/jwks.json"
                "/.well-known/jwks.json"
            ),
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


def test_clerk_verifier_appends_jwks_path_to_explicit_base_url() -> None:
    verifier = ClerkTokenVerifier(
        Settings(
            _env_file=None,
            clerk_jwks_url="https://modest-turkey-522.clerk.accounts.dev",
        )
    )

    assert verifier.jwks_url == (
        "https://modest-turkey-522.clerk.accounts.dev/.well-known/jwks.json"
    )


def test_clerk_verifier_keeps_issuer_fallback_when_explicit_jwks_is_set() -> None:
    verifier = ClerkTokenVerifier(
        Settings(
            _env_file=None,
            clerk_jwt_issuer="https://modest-turkey-522.clerk.accounts.dev",
            clerk_jwks_url="https://bad-clerk.example.com/.well-known/jwks.json",
        )
    )

    assert verifier.jwks_urls == [
        "https://bad-clerk.example.com/.well-known/jwks.json",
        "https://modest-turkey-522.clerk.accounts.dev/.well-known/jwks.json",
    ]


def test_clerk_verifier_ignores_pasted_env_name_in_issuer_value() -> None:
    verifier = ClerkTokenVerifier(
        Settings(
            _env_file=None,
            clerk_jwt_issuer=(
                "CLERK_JWT_ISSUER=https://modest-turkey-522.clerk.accounts.dev"
            ),
        )
    )

    assert verifier.issuer == "https://modest-turkey-522.clerk.accounts.dev"
    assert verifier.jwks_url == (
        "https://modest-turkey-522.clerk.accounts.dev/.well-known/jwks.json"
    )


def test_clerk_verifier_ignores_pasted_env_name_with_markdown_link() -> None:
    verifier = ClerkTokenVerifier(
        Settings(
            _env_file=None,
            clerk_jwt_issuer=(
                "CLERK_JWT_ISSUER="
                "[https://modest-turkey-522.clerk.accounts.dev/.well-known/jwks.json]"
                "(https://modest-turkey-522.clerk.accounts.dev/.well-known/jwks.json)"
            ),
        )
    )

    assert verifier.issuer == "https://modest-turkey-522.clerk.accounts.dev"
    assert verifier.jwks_url == (
        "https://modest-turkey-522.clerk.accounts.dev/.well-known/jwks.json"
    )


def test_split_token_rejects_malformed_signature() -> None:
    try:
        _split_token("header.payload.signature")
    except AuthError as exc:
        assert str(exc) == "invalid Clerk token"
    else:
        raise AssertionError("expected malformed signature to be rejected")
