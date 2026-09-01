from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from shared.errors import ConfigurationError


class TokenCipher:
    def __init__(self, key: str | None) -> None:
        if not key:
            raise ConfigurationError(
                "GOOGLE_TOKEN_ENCRYPTION_KEY is required for Gmail connections",
                {
                    "user_message": (
                        "Set GOOGLE_TOKEN_ENCRYPTION_KEY before connecting Gmail."
                    )
                },
            )
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except ValueError as exc:
            raise ConfigurationError(
                "GOOGLE_TOKEN_ENCRYPTION_KEY must be a valid Fernet key",
                {
                    "user_message": (
                        "Generate GOOGLE_TOKEN_ENCRYPTION_KEY with "
                        "`python -c \"from cryptography.fernet import Fernet; "
                        "print(Fernet.generate_key().decode())\"`."
                    )
                },
            ) from exc

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ConfigurationError(
                "stored Gmail token could not be decrypted",
                {"user_message": "Reconnect Gmail before sending outreach."},
            ) from exc
