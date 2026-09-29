from pydantic import BaseModel, ConfigDict, Field, field_validator


class SenderProfileUpdate(BaseModel):
    sender_legal_name: str | None = Field(default=None, max_length=255)
    sender_mailing_address: str | None = None
    sender_contact: str | None = Field(default=None, max_length=500)

    @field_validator("sender_legal_name", "sender_mailing_address", "sender_contact")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = " ".join((value or "").split())
        return normalized or None


class SenderProfileRead(SenderProfileUpdate):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: str
    complete: bool
