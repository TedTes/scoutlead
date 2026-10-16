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


class CallBranch(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    acknowledgement: str = Field(min_length=2, max_length=320)
    question: str | None = Field(default=None, min_length=2, max_length=320)
    value_hypothesis: str | None = Field(default=None, min_length=2, max_length=400)
    next_step: str | None = Field(default=None, min_length=2, max_length=320)
    terminal: bool = False


class CallDraft(BaseModel):
    opener: str = Field(min_length=8, max_length=240)
    observation: str = Field(min_length=8, max_length=320)
    ask: str = Field(min_length=8, max_length=240)
    permission: str | None = Field(default=None, min_length=8, max_length=240)
    discovery_question: str | None = Field(default=None, min_length=8, max_length=320)
    branches: list[CallBranch] = Field(default_factory=list, max_length=10)
    selected_branch: str | None = Field(default=None, max_length=80)


class OutreachStrategy(BaseModel):
    strategy_id: str
    strategy_version: int
    playbook_id: str
    playbook_version: int
    service_key: str
    primary_signal_key: str
    primary_signal_value: bool | int | float | str | None = None
    goal: str
    evidence_statement: str
    observation: str
    permission: str
    discovery_question: str
    seller_positioning: str
    value_hypothesis: str
    next_step: str
    permitted_claims: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)
    selected_variant: str
    renderer_version: int
    phrasing_provider: str
    call_branches: list[CallBranch] = Field(default_factory=list)


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
    strategy: OutreachStrategy | None = None


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
