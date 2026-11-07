from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


OutreachChannel = Literal["message", "call", "form", "email"]
OutreachDraftChannel = Literal["instagram", "sms", "email", "call"]
OutreachEventChannel = Literal[
    "instagram",
    "sms",
    "email",
    "call",
    "message",
    "form",
]
OutreachEventType = Literal[
    "channel_viewed",
    "draft_copied",
    "draft_edited",
    "response_classified",
    "follow_up_copied",
    "positive_reply",
    "negative_reply",
    "meeting_booked",
    "message_sent",
]


class OutreachEvidence(BaseModel):
    signal_key: str
    label: str
    statement: str
    value: bool | int | float | str | None = None


class WrittenDraft(BaseModel):
    body: str = Field(min_length=20, max_length=900)


class OutreachMessageTemplate(BaseModel):
    business_strength: str = Field(default="", max_length=1000)
    lead_reason: str = Field(default="", max_length=1000)
    opportunity: str = Field(default="", max_length=1000)
    proof_url: str | None = Field(default=None, max_length=2000)


class OutreachGenerationInput(BaseModel):
    channels: list[OutreachDraftChannel] = Field(
        default_factory=lambda: ["instagram"],
        min_length=1,
        max_length=4,
    )
    personal_detail: str | None = Field(default=None, max_length=1000)
    concept_url: str | None = Field(default=None, max_length=2000)
    concept_features: list[str] = Field(default_factory=list, max_length=8)
    persuasion_style: Literal[
        "friendly_adviser",
        "direct_specialist",
        "curious_consultant",
        "visual_demonstrator",
    ] = "friendly_adviser"
    structure_template_id: str | None = Field(default=None, max_length=64)
    message_structure: str | None = Field(default=None, max_length=4000)
    example_message: str | None = Field(default=None, max_length=6000)


class OutreachTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    structure: str = Field(min_length=10, max_length=4000)
    example: str | None = Field(default=None, max_length=6000)


class OutreachTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    structure: str | None = Field(default=None, min_length=10, max_length=4000)
    example: str | None = Field(default=None, max_length=6000)


class OutreachTemplateRead(BaseModel):
    id: str
    name: str
    structure: str
    example: str | None = None
    created_at: datetime
    updated_at: datetime


class OutreachProposal(BaseModel):
    positive_detail: str = Field(default="", max_length=1000)
    observed_opportunity: str = Field(min_length=8, max_length=1000)
    proposal_angle: str = Field(min_length=8, max_length=1000)
    proof_url: str | None = Field(default=None, max_length=2000)


class SocialChannelDraft(BaseModel):
    initial: str = Field(min_length=20, max_length=1200)
    follow_up: str = Field(min_length=10, max_length=600)


class SmsChannelDraft(BaseModel):
    initial: str = Field(min_length=20, max_length=320)
    follow_up: str = Field(min_length=10, max_length=240)


class EmailChannelDraft(BaseModel):
    subject: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=20, max_length=1600)
    follow_up_subject: str = Field(min_length=2, max_length=120)
    follow_up_body: str = Field(min_length=20, max_length=1000)


class CallChannelDraft(BaseModel):
    opener: str = Field(min_length=8, max_length=240)
    talking_points: list[str] = Field(min_length=1, max_length=6)
    close: str = Field(min_length=8, max_length=240)


class GeneratedSocialChannelDraft(BaseModel):
    initial: str = Field(min_length=20, max_length=700)
    follow_up: str = Field(min_length=10, max_length=320)

    @model_validator(mode="after")
    def enforce_word_limits(self):
        if len(self.initial.split()) > 110:
            raise ValueError("Instagram initial message must be 110 words or fewer")
        if len(self.follow_up.split()) > 45:
            raise ValueError("Instagram follow-up must be 45 words or fewer")
        return self


class GeneratedSmsChannelDraft(BaseModel):
    initial: str = Field(min_length=20, max_length=160)
    follow_up: str = Field(min_length=10, max_length=160)


class GeneratedEmailChannelDraft(BaseModel):
    subject: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=20, max_length=1200)
    follow_up_subject: str = Field(min_length=2, max_length=120)
    follow_up_body: str = Field(min_length=20, max_length=700)

    @model_validator(mode="after")
    def enforce_word_limits(self):
        if len(self.body.split()) > 180:
            raise ValueError("Email body must be 180 words or fewer")
        if len(self.follow_up_body.split()) > 90:
            raise ValueError("Email follow-up must be 90 words or fewer")
        return self


CallTalkingPoint = Annotated[str, Field(min_length=4, max_length=120)]


class GeneratedCallChannelDraft(BaseModel):
    opener: str = Field(min_length=8, max_length=160)
    talking_points: list[CallTalkingPoint] = Field(min_length=1, max_length=2)
    close: str = Field(min_length=8, max_length=120)

    @model_validator(mode="after")
    def enforce_spoken_length(self):
        words = " ".join([self.opener, *self.talking_points, self.close]).split()
        if len(words) > 65:
            raise ValueError("Call draft must be 65 words or fewer")
        return self


class OutreachChannelDrafts(BaseModel):
    instagram: SocialChannelDraft | None = None
    sms: SmsChannelDraft | None = None
    email: EmailChannelDraft | None = None
    call: CallChannelDraft | None = None


class GeneratedOutreachChannelDrafts(BaseModel):
    instagram: GeneratedSocialChannelDraft | None = None
    sms: GeneratedSmsChannelDraft | None = None
    email: GeneratedEmailChannelDraft | None = None
    call: GeneratedCallChannelDraft | None = None


class GeneratedOutreach(BaseModel):
    proposal: OutreachProposal
    channels: OutreachChannelDrafts
    prompt_version: int = Field(ge=1)


class GeneratedOutreachResponse(BaseModel):
    proposal: OutreachProposal
    channels: GeneratedOutreachChannelDrafts
    prompt_version: int = Field(ge=1)


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


class OutreachGeneration(BaseModel):
    message: WrittenDraft
    call: CallDraft
    form: WrittenDraft
    email: EmailDraft


class OutreachPackageContent(BaseModel):
    evidence_fingerprint: str = Field(min_length=64, max_length=64)
    observation: str = Field(min_length=8, max_length=320)
    evidence: list[OutreachEvidence] = Field(min_length=1, max_length=6)
    message_template: OutreachMessageTemplate | None = None
    outreach_input: OutreachGenerationInput = Field(default_factory=OutreachGenerationInput)
    generated_outreach: GeneratedOutreach | None = None
    message: WrittenDraft
    call: CallDraft | None = None
    form: WrittenDraft | None = None
    email: EmailDraft | None = None
    strategy: OutreachStrategy | None = None
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
    sent_channels: dict[OutreachDraftChannel, datetime] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class OutreachPackageUpdate(BaseModel):
    content: OutreachPackageContent


class OutreachMarkSentRequest(BaseModel):
    channel: OutreachDraftChannel


class OutreachGenerateRequest(BaseModel):
    outreach_input: OutreachGenerationInput = Field(default_factory=OutreachGenerationInput)


class OutreachResponseClassifyRequest(BaseModel):
    channel: OutreachChannel
    response_text: str = Field(min_length=1, max_length=4000)


class OutreachResponseClassification(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0, le=1)
    source: Literal["deterministic", "anthropic", "openai", "remote", "llm", "fallback"]
    suggested_reply: str | None = Field(default=None, max_length=1200)
    path: ReplyPath | None = None


class OutreachEventCreate(BaseModel):
    channel: OutreachEventChannel
    event_type: OutreachEventType
    variant_id: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutreachEventRead(BaseModel):
    id: str
    package_id: str
    channel: OutreachEventChannel
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
