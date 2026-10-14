from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


OutreachChannel = Literal["message", "call", "form", "email"]


class OutreachEvidence(BaseModel):
    signal_key: str
    label: str
    statement: str
    value: bool | int | float | str | None = None


class WrittenDraft(BaseModel):
    body: str = Field(min_length=20, max_length=900)


class EmailDraft(BaseModel):
    subject: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=20, max_length=1200)


class CallDraft(BaseModel):
    opener: str = Field(min_length=8, max_length=240)
    observation: str = Field(min_length=8, max_length=320)
    ask: str = Field(min_length=8, max_length=240)


class OutreachGeneration(BaseModel):
    message: WrittenDraft
    call: CallDraft
    form: WrittenDraft
    email: EmailDraft


class OutreachPackageContent(BaseModel):
    observation: str = Field(min_length=8, max_length=320)
    evidence: list[OutreachEvidence] = Field(min_length=1, max_length=6)
    message: WrittenDraft
    call: CallDraft | None = None
    form: WrittenDraft | None = None
    email: EmailDraft | None = None
    demo_path: str | None = None


class OutreachPackageRead(BaseModel):
    id: str
    audience_result_id: str
    business_id: str
    business_name: str
    website_url: str | None = None
    phone: str | None = None
    email: str | None = None
    contact_url: str | None = None
    channels: list[OutreachChannel]
    content: OutreachPackageContent
    provider: str
    model: str | None = None
    usage: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class OutreachPackageUpdate(BaseModel):
    content: OutreachPackageContent
