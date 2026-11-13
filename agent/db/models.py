from datetime import datetime
from typing import Any
from types import SimpleNamespace

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from db.base import Base, TimestampMixin
from db.types import EmbeddingVector


class UserModel(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    clerk_user_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspaces: Mapped[list["WorkspaceModel"]] = relationship(back_populates="owner")


class WorkspaceModel(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    clerk_organization_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    sender_legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_mailing_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_contact: Mapped[str | None] = mapped_column(String(500), nullable=True)

    owner: Mapped[UserModel | None] = relationship(back_populates="workspaces")
    products: Mapped[list["ProductModel"]] = relationship(back_populates="workspace")
    territories: Mapped[list["TerritoryModel"]] = relationship(back_populates="workspace")
    audience_folders: Mapped[list["AudienceFolderModel"]] = relationship(
        back_populates="workspace"
    )


class AdminAuditEventModel(TimestampMixin, Base):
    __tablename__ = "admin_audit_events"
    __table_args__ = (
        Index("ix_admin_audit_events_entity_created", "entity_type", "entity_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


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
    audience_folders: Mapped[list["AudienceFolderModel"]] = relationship(
        back_populates="product"
    )


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
    territory: Mapped["TerritoryModel | None"] = relationship(
        back_populates="campaigns",
        foreign_keys=[territory_id],
    )


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
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", index=True
    )
    is_chain: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    is_franchise: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    is_directory: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    is_agency: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
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
    attributes: Mapped[list["BusinessAttributeModel"]] = relationship(
        back_populates="business",
        cascade="all, delete-orphan",
    )


class SignalDefinitionModel(TimestampMixin, Base):
    """Collector and scoring metadata for a canonical business attribute.

    The physical table and class name are retained for migration/API
    compatibility. They do not store a signal assigned to a business; that
    state lives only in ``business_attributes``.
    """
    __tablename__ = "signal_definitions"
    __table_args__ = (
        UniqueConstraint("key", name="uq_signal_definitions_key"),
        Index("ix_signal_definitions_status_category", "status", "category"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    collector_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    extractor_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    freshness_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    opportunity_direction: Mapped[str] = mapped_column(
        String(32), nullable=False, default="none"
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# Preferred name for new code. Removing the legacy name/table would break
# queued jobs and historical migrations without changing the data model.
BusinessAttributeDefinitionModel = SignalDefinitionModel


class BusinessAttributeModel(TimestampMixin, Base):
    """One current business attribute with compact source provenance."""

    __tablename__ = "business_attributes"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "attribute_key",
            name="uq_business_attributes_business_key",
        ),
        Index("ix_business_attributes_key_text", "attribute_key", "value_text"),
        Index("ix_business_attributes_key_number", "attribute_key", "value_number"),
        Index("ix_business_attributes_key_boolean", "attribute_key", "value_boolean"),
        Index("ix_business_attributes_business_observed", "business_id", "observed_at"),
        Index(
            "ix_business_attributes_source_hash",
            "source_provider",
            "evidence_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    attribute_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    signal_definition_id: Mapped[str | None] = mapped_column(
        ForeignKey("signal_definitions.id"), nullable=True, index=True
    )
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    opportunity_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    score_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_provider: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_query_signature: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Compatibility names keep existing API payloads stable while the database
    # uses explicit attribute terminology.
    source = synonym("source_provider")
    external_id = synonym("source_external_id")
    query_signature = synonym("source_query_signature")
    content_hash = synonym("evidence_hash")
    attribute_score = synonym("opportunity_score")

    business: Mapped[BusinessModel] = relationship(back_populates="attributes")
    signal_definition: Mapped["SignalDefinitionModel | None"] = relationship()

    @property
    def raw_payload(self) -> dict[str, Any]:
        return self.evidence or self.value_json or {}

    @raw_payload.setter
    def raw_payload(self, value: dict[str, Any]) -> None:
        self.evidence = value

    @property
    def source_evidence_id(self) -> str | None:
        return self.id

    @source_evidence_id.setter
    def source_evidence_id(self, value: str | None) -> None:
        # Provenance now lives directly on the attribute row.
        pass

class AudienceResultModel(TimestampMixin, Base):
    __tablename__ = "audience_results"
    __table_args__ = (
        UniqueConstraint("audience_id", "business_id", name="uq_audience_results_audience_business"),
        UniqueConstraint("audience_id", "rank_position", name="uq_audience_results_audience_rank"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audience_id: Mapped[str] = mapped_column(
        ForeignKey("territories.id"), nullable=False, index=True
    )
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False)
    match_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    outreach_lead_id: Mapped[str | None] = mapped_column(
        ForeignKey("leads.id"), nullable=True, index=True
    )


class OutreachTemplateModel(TimestampMixin, Base):
    __tablename__ = "outreach_templates"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "name",
            name="uq_outreach_templates_workspace_name",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    structure: Mapped[str] = mapped_column(Text, nullable=False)
    example: Mapped[str | None] = mapped_column(Text, nullable=True)


class NicheModel(TimestampMixin, Base):
    __tablename__ = "niches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    default_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    catalog_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="supported", index=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_workspace_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    signal_vocabulary: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    search_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    memberships: Mapped[list["BusinessNicheMembershipModel"]] = relationship(
        back_populates="niche"
    )
    territories: Mapped[list["TerritoryModel"]] = relationship(back_populates="niche")


class WorkspaceNichePreferenceModel(Base):
    __tablename__ = "workspace_niche_preferences"

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    niche_id: Mapped[str] = mapped_column(
        ForeignKey("niches.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AudienceFolderModel(TimestampMixin, Base):
    __tablename__ = "audience_folders"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "product_id",
            "name",
            name="uq_audience_folders_workspace_product_name",
        ),
        UniqueConstraint(
            "workspace_id",
            "product_id",
            "niche_id",
            name="uq_audience_folders_workspace_product_niche",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    niche_id: Mapped[str | None] = mapped_column(
        ForeignKey("niches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    workspace: Mapped[WorkspaceModel] = relationship(back_populates="audience_folders")
    product: Mapped[ProductModel] = relationship(back_populates="audience_folders")
    audiences: Mapped[list["TerritoryModel"]] = relationship(back_populates="folder")


class TerritoryModel(TimestampMixin, Base):
    __tablename__ = "territories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("audience_folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    niche_id: Mapped[str] = mapped_column(ForeignKey("niches.id"), nullable=False, index=True)
    market_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    place_label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    place_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    place_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    radius_km: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    locations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    customer_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="residential", index=True
    )
    min_google_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    service_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    signal_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    exclusion_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    cadence: Mapped[str] = mapped_column(String(32), nullable=False, default="weekly")
    refill_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="when_depleted", index=True
    )
    criteria_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    min_fit: Mapped[str] = mapped_column(String(32), nullable=False, default="maybe")
    search_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_contract: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evidence_max_age_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    criteria_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    match_state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    match_requested_count: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    match_result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    match_new_result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    match_index_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    match_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    match_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    match_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    match_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    outreach_campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "campaigns.id",
            name="fk_territories_outreach_campaign_id_campaigns",
            use_alter=True,
        ),
        nullable=True,
        index=True,
    )

    workspace: Mapped[WorkspaceModel] = relationship(back_populates="territories")
    product: Mapped[ProductModel] = relationship(back_populates="territories")
    folder: Mapped[AudienceFolderModel | None] = relationship(back_populates="audiences")
    niche: Mapped[NicheModel] = relationship(back_populates="territories")
    campaigns: Mapped[list[CampaignModel]] = relationship(
        back_populates="territory",
        foreign_keys=[CampaignModel.territory_id],
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
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    business: Mapped[BusinessModel] = relationship(back_populates="niche_memberships")
    niche: Mapped[NicheModel] = relationship(back_populates="memberships")


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
    decision_stage: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    decision: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision_details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    decision_actor_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    business: Mapped[BusinessModel | None] = relationship()

    @property
    def decisions(self) -> list[SimpleNamespace]:
        """Compatibility view of the single current decision stored on the item."""
        if self.decision is None:
            return []
        return [
            SimpleNamespace(
                id=f"{self.id}:decision",
                source_item_id=self.id,
                stage=self.decision_stage,
                decision=self.decision,
                reason=self.decision_reason,
                confidence=self.decision_confidence,
                details=self.decision_details or {},
                actor_type=self.decision_actor_type or "system",
                actor_id=self.decision_actor_id,
                created_at=self.decided_at or self.updated_at,
                updated_at=self.decided_at or self.updated_at,
            )
        ]


class LeadModel(TimestampMixin, Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
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
    follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    recorded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


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


class MessageModel(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), nullable=False, index=True)
    audience_result_id: Mapped[str | None] = mapped_column(
        ForeignKey("audience_results.id", ondelete="SET NULL"), nullable=True, index=True
    )
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
    generation_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generation_usage: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generation_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    @property
    def content(self) -> dict[str, Any]:
        value = (self.generation_context or {}).get("content")
        return value if isinstance(value, dict) else {}

    @content.setter
    def content(self, value: dict[str, Any]) -> None:
        self.generation_context = {**(self.generation_context or {}), "content": value}

    @property
    def provider(self) -> str:
        return self.generation_provider or "template"

    @provider.setter
    def provider(self, value: str) -> None:
        self.generation_provider = value

    @property
    def model(self) -> str | None:
        return self.generation_model

    @model.setter
    def model(self, value: str | None) -> None:
        self.generation_model = value

    @property
    def usage(self) -> dict[str, Any]:
        return self.generation_usage or {}

    @usage.setter
    def usage(self, value: dict[str, Any]) -> None:
        self.generation_usage = value


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


class QueueJobModel(TimestampMixin, Base):
    __tablename__ = "queue_jobs"
    __table_args__ = (
        Index(
            "ix_queue_jobs_poll",
            "status",
            "run_after",
            "created_at",
        ),
        Index(
            "uq_queue_jobs_active_idempotency",
            "idempotency_key",
            unique=True,
            postgresql_where=text(
                "idempotency_key IS NOT NULL AND status IN ('queued', 'running')"
            ),
            sqlite_where=text(
                "idempotency_key IS NOT NULL AND status IN ('queued', 'running')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parent_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
