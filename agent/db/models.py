from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin


class ProductModel(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_description: Mapped[str] = mapped_column(Text, nullable=False)
    target_customer: Mapped[str] = mapped_column(String(500), nullable=False)
    problem_being_solved: Mapped[str] = mapped_column(Text, nullable=False)
    value_proposition: Mapped[str] = mapped_column(Text, nullable=False)
    target_geography: Mapped[str] = mapped_column(String(255), nullable=False)
    validation_goal: Mapped[str] = mapped_column(Text, nullable=False)
    qualification_criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    preferred_discovery_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    outreach_objective: Mapped[str] = mapped_column(Text, nullable=False)
    constraints: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CampaignModel(TimestampMixin, Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    max_leads: Mapped[int] = mapped_column(Integer, nullable=False)
    channels: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    discovery_seeds: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    goal_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    product: Mapped[ProductModel] = relationship()


class LeadModel(TimestampMixin, Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    website_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    geography: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    research: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    qualification: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class MessageModel(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    personalization_notes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    approach_tag: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    approval: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConversationModel(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)

    events: Mapped[list["ConversationEventModel"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationEventModel.created_at",
    )


class ConversationEventModel(Base):
    __tablename__ = "conversation_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    conversation: Mapped[ConversationModel] = relationship(back_populates="events")


class CampaignMemoryModel(Base):
    __tablename__ = "campaign_memory"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    score_impact: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LearningSummaryModel(TimestampMixin, Base):
    __tablename__ = "learning_summaries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class QueueJobModel(TimestampMixin, Base):
    __tablename__ = "queue_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRunModel(TimestampMixin, Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    current_phase: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    max_llm_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    max_leads: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentStepModel(TimestampMixin, Base):
    __tablename__ = "agent_steps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    observation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolCallModel(TimestampMixin, Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), nullable=False, index=True)
    step_id: Mapped[str | None] = mapped_column(ForeignKey("agent_steps.id"), nullable=True, index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    args: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    observation: Mapped[dict[str, Any] | list[Any] | str | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
