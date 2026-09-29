from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LeadOutcome(StrEnum):
    CONTACTED = "contacted"
    NO_RESPONSE = "no_response"
    REPLIED_POSITIVE = "replied_positive"
    REPLIED_NEGATIVE = "replied_negative"
    MEETING_BOOKED = "meeting_booked"
    WON = "won"
    NOT_A_FIT = "not_a_fit"
    WRONG_CONTACT = "wrong_contact"
    BUSINESS_CLOSED = "business_closed"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"


class OutcomeChannel(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    VISIT = "visit"
    CONTACT_FORM = "contact_form"
    OTHER = "other"


class OutcomeSource(StrEnum):
    MANUAL = "manual"
    EMAIL_SEND = "email_send"
    REPLY_SYNC = "reply_sync"
    UNSUBSCRIBE_LINK = "unsubscribe_link"
    BOUNCE = "bounce"
    SYSTEM = "system"


class LeadOutcomeCreate(BaseModel):
    outcome: LeadOutcome
    channel: OutcomeChannel = OutcomeChannel.OTHER
    source: OutcomeSource = OutcomeSource.MANUAL
    note: str | None = Field(default=None, max_length=2000)
    occurred_at: datetime | None = None


class LeadOutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    product_id: str
    lead_id: str
    business_id: str | None = None
    territory_id: str | None = None
    niche_id: str | None = None
    market_key: str | None = None
    outcome: LeadOutcome
    channel: OutcomeChannel
    source: OutcomeSource
    note: str | None = None
    occurred_at: datetime
    recorded_by: str | None = None
    created_at: datetime
    updated_at: datetime
