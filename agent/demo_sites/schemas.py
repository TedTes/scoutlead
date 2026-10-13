from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class DemoService(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=10, max_length=240)


class DemoSiteContent(BaseModel):
    business_name: str = Field(min_length=1, max_length=160)
    eyebrow: str = Field(max_length=80)
    headline: str = Field(min_length=8, max_length=120)
    subheadline: str = Field(min_length=15, max_length=280)
    primary_cta: str = Field(min_length=2, max_length=40)
    services: list[DemoService] = Field(min_length=1, max_length=6)
    trust_heading: str = Field(max_length=100)
    trust_body: str = Field(max_length=320)
    contact_heading: str = Field(max_length=100)
    palette: Literal["green", "blue", "charcoal", "red"] = "green"


class DemoGeneration(BaseModel):
    site: DemoSiteContent
    outreach_message: str = Field(min_length=20, max_length=900)


class DemoSiteRead(BaseModel):
    id: str
    status: Literal["draft", "published", "expired"]
    share_token: str
    content: DemoSiteContent
    outreach_message: str
    usage: dict
    view_count: int = 0
    last_viewed_at: datetime | None = None
    published_at: datetime | None = None
    expires_at: datetime | None = None


class DemoSiteUpdate(BaseModel):
    content: DemoSiteContent | None = None
    outreach_message: str | None = Field(default=None, min_length=20, max_length=900)
