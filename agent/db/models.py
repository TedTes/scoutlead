from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin
from db.types import EmbeddingVector


class UserModel(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    clerk_user_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list["WorkspaceMemberModel"]] = relationship(back_populates="user")


class WorkspaceModel(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    clerk_organization_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    sender_legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_mailing_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_contact: Mapped[str | None] = mapped_column(String(500), nullable=True)

    memberships: Mapped[list["WorkspaceMemberModel"]] = relationship(back_populates="workspace")
    products: Mapped[list["ProductModel"]] = relationship(back_populates="workspace")
    territories: Mapped[list["TerritoryModel"]] = relationship(back_populates="workspace")


class WorkspaceMemberModel(TimestampMixin, Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="owner")

    workspace: Mapped[WorkspaceModel] = relationship(back_populates="memberships")
    user: Mapped[UserModel] = relationship(back_populates="memberships")


class ProductModel(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "source_fingerprint",
            name="uq_products_workspace_source_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id"), nullable=True, index=True
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_customer: Mapped[str] = mapped_column(String(500), nullable=False)
    problem_being_solved: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_proposition: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_geography: Mapped[str] = mapped_column(String(255), nullable=False)
    validation_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    preferred_discovery_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    outreach_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    offer_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ideal_customer_signals: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    exclusions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    typical_deal_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[WorkspaceModel | None] = relationship(back_populates="products")
    territories: Mapped[list["TerritoryModel"]] = relationship(back_populates="product")


class ProductSourceDraftModel(TimestampMixin, Base):
    __tablename__ = "product_source_drafts"
    __table_args__ = (
        UniqueConstraint(
            "source_fingerprint",
            "context_fingerprint",
            name="uq_product_source_drafts_source_context",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_geography: Mapped[str] = mapped_column(String(255), nullable=False)
    inference: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class CampaignModel(TimestampMixin, Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    territory_id: Mapped[str | None] = mapped_column(
        ForeignKey("territories.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    goal_type: Mapped[str] = mapped_column(String(32), nullable=False, default="learn")
    icp_preset_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_preset_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_inputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    max_leads: Mapped[int] = mapped_column(Integer, nullable=False)
    channels: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    discovery_seeds: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    goal_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    product: Mapped[ProductModel] = relationship()
    territory: Mapped["TerritoryModel | None"] = relationship(back_populates="campaigns")


class CampaignSourceModel(TimestampMixin, Base):
    __tablename__ = "campaign_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(64), nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    budget_limit: Mapped[float | None] = mapped_column(Float, nullable=True)


class BusinessModel(TimestampMixin, Base):
    __tablename__ = "businesses"
    __table_args__ = (
        UniqueConstraint("normalized_name", "domain", name="uq_businesses_normalized_name_domain"),
        Index(
            "ix_businesses_status_market_category",
            "status",
            "market_key",
            "category_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    website_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    geography: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    category_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    market_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    semantic_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingVector(1536), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    contacts: Mapped[list["ContactModel"]] = relationship(back_populates="business")
    niche_memberships: Mapped[list["BusinessNicheMembershipModel"]] = relationship(
        back_populates="business"
    )
    facts: Mapped[list["BusinessFactModel"]] = relationship(back_populates="business")


class BusinessFactModel(TimestampMixin, Base):
    __tablename__ = "business_facts"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "fact_key",
            name="uq_business_facts_business_key",
        ),
        Index("ix_business_facts_key_text", "fact_key", "value_text"),
        Index("ix_business_facts_key_number", "fact_key", "value_number"),
        Index("ix_business_facts_key_boolean", "fact_key", "value_boolean"),
        Index("ix_business_facts_business_observed", "business_id", "observed_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    fact_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_observations.id"), nullable=True, index=True
    )
    resolver_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    business: Mapped[BusinessModel] = relationship(back_populates="facts")
    source_observation: Mapped["SourceObservationModel | None"] = relationship()


class BusinessSearchEvaluationModel(TimestampMixin, Base):
    __tablename__ = "business_search_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "contract_hash",
            "evidence_fingerprint",
            name="uq_business_search_evaluations_evidence",
        ),
        Index(
            "ix_business_search_evaluations_contract_status",
            "contract_hash",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    contract_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    criterion_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    missing_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    business: Mapped[BusinessModel] = relationship()


class NicheModel(TimestampMixin, Base):
    __tablename__ = "niches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    default_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    signal_vocabulary: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    memberships: Mapped[list["BusinessNicheMembershipModel"]] = relationship(
        back_populates="niche"
    )
    seed_batches: Mapped[list["SeedBatchModel"]] = relationship(back_populates="niche")
    territories: Mapped[list["TerritoryModel"]] = relationship(back_populates="niche")


class TerritoryModel(TimestampMixin, Base):
    __tablename__ = "territories"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "product_id",
            "niche_id",
            "market_key",
            "criteria_hash",
            name="uq_territories_workspace_offer_niche_market_criteria",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    niche_id: Mapped[str] = mapped_column(ForeignKey("niches.id"), nullable=False, index=True)
    market_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    cadence: Mapped[str] = mapped_column(String(32), nullable=False, default="weekly")
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    min_fit: Mapped[str] = mapped_column(String(32), nullable=False, default="maybe")
    search_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_contract: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evidence_max_age_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    criteria_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[WorkspaceModel] = relationship(back_populates="territories")
    product: Mapped[ProductModel] = relationship(back_populates="territories")
    niche: Mapped[NicheModel] = relationship(back_populates="territories")
    campaigns: Mapped[list[CampaignModel]] = relationship(back_populates="territory")
    deliveries: Mapped[list["TerritoryDeliveryModel"]] = relationship(
        back_populates="territory"
    )


class TerritoryDeliveryModel(TimestampMixin, Base):
    __tablename__ = "territory_deliveries"
    __table_args__ = (
        UniqueConstraint("campaign_id", name="uq_territory_deliveries_campaign_id"),
        UniqueConstraint(
            "territory_id",
            "scheduled_for",
            name="uq_territory_deliveries_territory_schedule",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    territory_id: Mapped[str] = mapped_column(
        ForeignKey("territories.id"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False, index=True
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_contact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled", index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    territory: Mapped[TerritoryModel] = relationship(back_populates="deliveries")
    campaign: Mapped[CampaignModel] = relationship()


class SeedBatchModel(TimestampMixin, Base):
    __tablename__ = "seed_batches"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    niche_id: Mapped[str | None] = mapped_column(ForeignKey("niches.id"), nullable=True, index=True)
    market_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="manual_seed",
        index=True,
    )
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    found_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    niche: Mapped[NicheModel | None] = relationship(back_populates="seed_batches")
    memberships: Mapped[list["BusinessNicheMembershipModel"]] = relationship(
        back_populates="seed_batch"
    )


class BusinessNicheMembershipModel(TimestampMixin, Base):
    __tablename__ = "business_niche_memberships"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "niche_id",
            "market_key",
            name="uq_business_niche_memberships_business_niche_market",
        ),
        Index(
            "ix_business_niche_memberships_niche_market",
            "niche_id",
            "market_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"),
        nullable=False,
        index=True,
    )
    niche_id: Mapped[str] = mapped_column(ForeignKey("niches.id"), nullable=False, index=True)
    market_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="unknown",
        index=True,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    source_observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_observations.id"),
        nullable=True,
        index=True,
    )
    seed_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("seed_batches.id"),
        nullable=True,
        index=True,
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    business: Mapped[BusinessModel] = relationship(back_populates="niche_memberships")
    niche: Mapped[NicheModel] = relationship(back_populates="memberships")
    source_observation: Mapped["SourceObservationModel | None"] = relationship(
        "SourceObservationModel"
    )
    seed_batch: Mapped[SeedBatchModel | None] = relationship(back_populates="memberships")


class BusinessIndexSegmentModel(TimestampMixin, Base):
    __tablename__ = "business_index_segments"
    __table_args__ = (
        UniqueConstraint(
            "niche_id",
            "market_key",
            name="uq_business_index_segments_niche_market",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    niche_id: Mapped[str] = mapped_column(ForeignKey("niches.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    market_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    market_label: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    demand_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_business_count: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    source_plan: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    source_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_refresh_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    niche: Mapped[NicheModel] = relationship()
    product: Mapped[ProductModel] = relationship()


class ContactModel(TimestampMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("business_id", "email", name="uq_contacts_business_email"),
        Index(
            "ix_contacts_business_verification",
            "business_id",
            "verification_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unverified")
    verification_provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    business: Mapped[BusinessModel] = relationship(back_populates="contacts")


class SourceObservationModel(TimestampMixin, Base):
    __tablename__ = "source_observations"
    __table_args__ = (
        Index(
            "ix_source_observations_business_observed",
            "business_id",
            "observed_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    query_signature: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    business: Mapped[BusinessModel] = relationship()


class SourceItemModel(TimestampMixin, Base):
    __tablename__ = "source_items"
    __table_args__ = (
        Index("ix_source_items_segment_state", "segment_id", "state"),
        Index("ix_source_items_provider_fetched", "provider_id", "fetched_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    segment_id: Mapped[str] = mapped_column(
        ForeignKey("business_index_segments.id"), nullable=False, index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("queue_jobs.id"), nullable=True, index=True
    )
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    business: Mapped[BusinessModel | None] = relationship()
    decisions: Mapped[list["SourceItemDecisionModel"]] = relationship(
        back_populates="source_item",
        order_by="SourceItemDecisionModel.created_at",
    )


class SourceItemDecisionModel(TimestampMixin, Base):
    __tablename__ = "source_item_decisions"
    __table_args__ = (
        Index(
            "ix_source_item_decisions_item_stage_created",
            "source_item_id",
            "stage",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_item_id: Mapped[str] = mapped_column(
        ForeignKey("source_items.id"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    source_item: Mapped[SourceItemModel] = relationship(back_populates="decisions")


class LeadModel(TimestampMixin, Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    territory_id: Mapped[str | None] = mapped_column(
        ForeignKey("territories.id"), nullable=True, index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    business_id: Mapped[str | None] = mapped_column(ForeignKey("businesses.id"), nullable=True, index=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"), nullable=True, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    website_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    geography: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unreviewed")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shortlisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contact_policy_status: Mapped[str] = mapped_column(String(32), nullable=False, default="allowed")
    contact_policy_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_policy_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unverified")
    verification_provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    raw_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    research: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    qualification: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    latest_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    latest_outcome_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approach: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    outcome_adjustment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rank_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)


class LeadOutcomeModel(TimestampMixin, Base):
    __tablename__ = "lead_outcomes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), nullable=False, index=True)
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    territory_id: Mapped[str | None] = mapped_column(
        ForeignKey("territories.id"), nullable=True, index=True
    )
    niche_id: Mapped[str | None] = mapped_column(ForeignKey("niches.id"), nullable=True, index=True)
    market_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    recorded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class OutcomeModel(TimestampMixin, Base):
    __tablename__ = "outcome_models"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "product_id",
            "niche_id",
            name="uq_outcome_models_workspace_product_niche",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    niche_id: Mapped[str] = mapped_column(ForeignKey("niches.id"), nullable=False, index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    n_contacted: Mapped[int] = mapped_column(Integer, nullable=False)
    n_positive: Mapped[int] = mapped_column(Integer, nullable=False)
    weights: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)


class ContactSuppressionModel(TimestampMixin, Base):
    __tablename__ = "contact_suppressions"
    __table_args__ = (
        UniqueConstraint(
            "scope",
            "workspace_id",
            "product_id",
            "kind",
            "value",
            name="uq_contact_suppressions_scope_workspace_product_kind_value",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id"), nullable=True, index=True
    )
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")

    product: Mapped[ProductModel | None] = relationship()
    lead: Mapped[LeadModel | None] = relationship()
    workspace: Mapped[WorkspaceModel | None] = relationship()


class WebhookDeliveryModel(TimestampMixin, Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped[ProductModel] = relationship()
    campaign: Mapped[CampaignModel] = relationship()


class DiscoveryCandidateModel(TimestampMixin, Base):
    __tablename__ = "discovery_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    geography: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    candidate_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class EmailConnectionModel(TimestampMixin, Base):
    __tablename__ = "email_connections"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", name="uq_email_connections_workspace_provider"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email_address: Mapped[str] = mapped_column(String(320), nullable=False)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    workspace: Mapped[WorkspaceModel] = relationship()
    product: Mapped[ProductModel] = relationship()


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


class CampaignInsightModel(TimestampMixin, Base):
    __tablename__ = "campaign_insights"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    goal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    icp_verdict: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    metrics_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
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


class RunPipelineEventModel(TimestampMixin, Base):
    __tablename__ = "run_pipeline_events"
    __table_args__ = (
        Index(
            "ix_run_pipeline_events_campaign_created",
            "campaign_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False, index=True
    )
    segment_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_index_segments.id"), nullable=True, index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("queue_jobs.id"), nullable=True, index=True
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    lead_id: Mapped[str | None] = mapped_column(
        ForeignKey("leads.id"), nullable=True, index=True
    )
    item_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


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
