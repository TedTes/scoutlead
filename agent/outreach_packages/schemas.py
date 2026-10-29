from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


OutreachChannel = Literal["message", "call", "form", "email"]
OutreachEventType = Literal[
    "channel_viewed",
    "draft_copied",
    "draft_edited",
    "response_classified",
    "follow_up_copied",
    "positive_reply",
    "negative_reply",
    "meeting_booked",
]


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


class OutreachClaim(BaseModel):
    text: str = Field(min_length=2, max_length=500)
    kind: Literal["evidence", "hypothesis", "seller", "cta"]
    evidence_keys: list[str] = Field(default_factory=list)


class ReplyPath(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    acknowledgement: str = Field(min_length=2, max_length=320)
    question: str | None = Field(default=None, min_length=2, max_length=320)
    value_hypothesis: str | None = Field(default=None, min_length=2, max_length=400)
    next_step: str | None = Field(default=None, min_length=2, max_length=320)
    terminal: bool = False
    keywords: list[str] = Field(default_factory=list)
    channel_replies: dict[OutreachChannel, str] = Field(default_factory=dict)


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
    uncertainty_clause: str | None = None
    customer_consequence: str
    permission: str
    discovery_question: str
    seller_positioning: str
    value_hypothesis: str
    next_step: str
    trade_key: str
    customer_actions: list[str] = Field(default_factory=list)
    permitted_claims: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)
    claim_ledger: list[OutreachClaim] = Field(default_factory=list)
    selected_variant: str
    selected_variants: dict[str, int] = Field(default_factory=dict)
    experiment_id: str | None = None
    renderer_version: int
    phrasing_provider: str
    call_branches: list[CallBranch] = Field(default_factory=list)
    reply_paths: list[ReplyPath] = Field(default_factory=list)


class DraftAlternative(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=80)
    channel: OutreachChannel
    body: str = Field(min_length=8, max_length=1200)
    subject: str | None = Field(default=None, min_length=2, max_length=120)


class OutreachGeneration(BaseModel):
    message: WrittenDraft
    call: CallDraft
    form: WrittenDraft
    email: EmailDraft


class OutreachPackageContent(BaseModel):
    evidence_fingerprint: str = Field(min_length=64, max_length=64)
    observation: str = Field(min_length=8, max_length=320)
    evidence: list[OutreachEvidence] = Field(min_length=1, max_length=6)
    message: WrittenDraft
    call: CallDraft | None = None
    form: WrittenDraft | None = None
    email: EmailDraft | None = None
    strategy: OutreachStrategy | None = None
    alternatives: list[DraftAlternative] = Field(default_factory=list, max_length=12)
    reply_paths: list[ReplyPath] = Field(default_factory=list, max_length=10)


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


class OutreachAISuggestionRequest(BaseModel):
    channel: Literal["message", "form", "email"]


class OutreachResponseClassifyRequest(BaseModel):
    channel: OutreachChannel
    response_text: str = Field(min_length=1, max_length=4000)


class OutreachResponseClassification(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0, le=1)
    source: Literal["deterministic", "openai", "fallback"]
    suggested_reply: str | None = Field(default=None, max_length=1200)
    path: ReplyPath | None = None


class OutreachEventCreate(BaseModel):
    channel: OutreachChannel
    event_type: OutreachEventType
    variant_id: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutreachEventRead(BaseModel):
    id: str
    package_id: str
    channel: OutreachChannel
    event_type: OutreachEventType
    variant_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class OutreachAnalyticsRead(BaseModel):
    total_events: int
    by_event: dict[str, int]
    by_channel: dict[str, int]
    by_variant: dict[str, int]


class PlaybookAdminRead(BaseModel):
    id: str | None = None
    service_key: str
    version: int
    status: Literal["default", "draft", "active", "inactive"]
    definition: dict[str, Any]
    updated_at: datetime | None = None


class PlaybookAdminUpdate(BaseModel):
    definition: dict[str, Any]
    reason: str = Field(min_length=3, max_length=1000)


class PlaybookAdminStateChange(BaseModel):
    status: Literal["draft", "active", "inactive"]
    reason: str = Field(min_length=3, max_length=1000)
