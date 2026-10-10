from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from admin.schemas import AdminBusinessCreate, AdminBusinessUpdate
from auth.context import AuthContext
from canonical.normalization import normalize_business_name, normalize_domain, normalize_phone
from db.base import Base
from db.models import (
    AdminAuditEventModel,
    BusinessFactModel,
    BusinessIndexSegmentModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    BusinessPublicationModel,
    NicheModel,
    SourceItemModel,
    ValidationResultModel,
)
from publication.validation import BusinessValidationService
from shared.errors import ConflictError, NotFoundError, ValidationError
from shared.utils import new_id, normalize_url, utcnow
from source_items.repository import source_item_content_hash
from source_items.schemas import SourceItemCreate


REQUIRED_VALIDATIONS = {"identity", "business_identity", "trade", "location"}
SOURCE_PRIORITY = {
    "google_places": 0,
    "google_places_seed": 1,
    "company_website_seed": 2,
    "openstreetmap_seed": 3,
    "configured_search": 4,
    "website_presence_check": 5,
    "admin_manual": 6,
    "kijiji": 7,
}


class AdminDataService:
    def __init__(self, session: Session, auth: AuthContext) -> None:
        self.session = session
        self.auth = auth

    def overview(self) -> dict[str, Any]:
        businesses = list(self.session.scalars(select(BusinessModel)))
        states = self._validation_states([business.id for business in businesses])
        status_counts = Counter(business.status for business in businesses)
        validation_counts = Counter(states[business.id]["state"] for business in businesses)
        return {
            "total": len(businesses),
            "active": status_counts["active"],
            "quarantined": status_counts["quarantined"],
            "archived": status_counts["archived"],
            "fully_validated": validation_counts["passed"],
            "needs_attention": validation_counts["attention"],
            "incomplete": validation_counts["incomplete"],
            "published": self.session.scalar(
                select(func.count()).select_from(BusinessPublicationModel).where(
                    BusinessPublicationModel.status == "published"
                )
            ) or 0,
        }

    def list_businesses(
        self,
        *,
        query: str | None,
        validation: str | None,
        status: str | None,
        niche_slug: str | None,
        market_key: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        statement = select(BusinessModel)
        if query:
            pattern = f"%{query.strip()}%"
            statement = statement.where(
                or_(
                    BusinessModel.display_name.ilike(pattern),
                    BusinessModel.address.ilike(pattern),
                    BusinessModel.domain.ilike(pattern),
                    BusinessModel.phone.ilike(pattern),
                )
            )
        if status:
            statement = statement.where(BusinessModel.status == status)
        if niche_slug or market_key:
            statement = statement.join(
                BusinessNicheMembershipModel,
                BusinessNicheMembershipModel.business_id == BusinessModel.id,
            ).join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
            if niche_slug:
                statement = statement.where(NicheModel.slug == niche_slug)
            if market_key:
                statement = statement.where(BusinessNicheMembershipModel.market_key == market_key)
        businesses = list(
            self.session.scalars(statement.distinct().order_by(BusinessModel.display_name))
        )
        states = self._validation_states([business.id for business in businesses])
        memberships = self._primary_memberships([business.id for business in businesses])
        rows = [
            self._business_summary(business, states[business.id], memberships.get(business.id))
            for business in businesses
        ]
        if validation:
            rows = [row for row in rows if row["validation_state"] == validation]
        total = len(rows)
        start = (page - 1) * page_size
        return {
            "items": rows[start : start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def detail(self, business_id: str) -> dict[str, Any]:
        business = self._business(business_id)
        state = self._validation_states([business_id])[business_id]
        memberships = list(
            self.session.execute(
                select(BusinessNicheMembershipModel, NicheModel)
                .join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
                .where(BusinessNicheMembershipModel.business_id == business_id)
            )
        )
        facts = list(
            self.session.scalars(
                select(BusinessFactModel)
                .where(BusinessFactModel.business_id == business_id)
                .order_by(BusinessFactModel.fact_key)
            )
        )
        sources = list(
            self.session.scalars(
                select(SourceItemModel)
                .where(SourceItemModel.business_id == business_id)
                .order_by(SourceItemModel.fetched_at.desc())
                .limit(30)
            )
        )
        publications = list(
            self.session.scalars(
                select(BusinessPublicationModel)
                .where(BusinessPublicationModel.business_id == business_id)
                .order_by(BusinessPublicationModel.evaluated_at.desc())
            )
        )
        audit = list(
            self.session.scalars(
                select(AdminAuditEventModel)
                .where(
                    AdminAuditEventModel.entity_type == "business",
                    AdminAuditEventModel.entity_id == business_id,
                )
                .order_by(AdminAuditEventModel.created_at.desc())
                .limit(50)
            )
        )
        return {
            **self._business_summary(business, state, memberships[0] if memberships else None),
            "normalized_name": business.normalized_name,
            "latitude": business.latitude,
            "longitude": business.longitude,
            "customer_kind": business.customer_kind,
            "is_chain": business.is_chain,
            "is_franchise": business.is_franchise,
            "is_directory": business.is_directory,
            "is_agency": business.is_agency,
            "memberships": [
                {
                    "id": membership.id,
                    "niche_slug": niche.slug,
                    "niche_label": niche.label,
                    "market_key": membership.market_key,
                    "confidence": membership.confidence,
                }
                for membership, niche in memberships
            ],
            "validations": state["validations"],
            "facts": [
                {
                    "id": fact.id,
                    "key": fact.fact_key,
                    "value": _fact_value(fact),
                    "confidence": fact.confidence,
                    "resolution_state": fact.resolution_state,
                    "quality_state": fact.quality_state,
                    "observed_at": fact.observed_at,
                    "expires_at": fact.expires_at,
                }
                for fact in facts
            ],
            "sources": [
                {
                    "id": item.id,
                    "provider": item.provider_id,
                    "state": item.state,
                    "source_url": item.source_url,
                    "title": item.title,
                    "fetched_at": item.fetched_at,
                    "last_error": item.last_error,
                }
                for item in sources
            ],
            "publications": [
                {
                    "id": publication.id,
                    "niche_id": publication.niche_id,
                    "market_key": publication.market_key,
                    "status": publication.status,
                    "reasons": publication.reasons,
                    "evaluated_at": publication.evaluated_at,
                    "expires_at": publication.expires_at,
                }
                for publication in publications
            ],
            "audit": [
                {
                    "id": event.id,
                    "action": event.action,
                    "reason": event.reason,
                    "actor_email": event.actor_email,
                    "before": event.before,
                    "after": event.after,
                    "created_at": event.created_at,
                }
                for event in audit
            ],
            "delete_dependencies": {},
        }

    def create(self, data: AdminBusinessCreate) -> dict[str, Any]:
        segment = self.session.scalar(
            select(BusinessIndexSegmentModel)
            .join(NicheModel, NicheModel.id == BusinessIndexSegmentModel.niche_id)
            .where(NicheModel.slug == data.niche_slug, BusinessIndexSegmentModel.market_key == data.market_key)
            .limit(1)
        )
        if segment is None:
            raise ValidationError("No business index segment exists for this niche and market")
        normalized_name = normalize_business_name(data.display_name)
        domain = normalize_domain(data.website_url)
        duplicate = self.session.scalar(
            select(BusinessModel).where(
                BusinessModel.normalized_name == normalized_name,
                BusinessModel.market_key == data.market_key,
            ).limit(1)
        )
        if duplicate is not None:
            raise ConflictError("A matching canonical business already exists", {"business_id": duplicate.id})
        now = utcnow()
        business = BusinessModel(
            id=new_id("business"),
            display_name=data.display_name.strip(),
            normalized_name=normalized_name,
            website_url=normalize_url(data.website_url),
            domain=domain,
            phone=normalize_phone(data.phone),
            address=data.address,
            geography=data.geography,
            category_key=data.niche_slug,
            market_key=data.market_key,
            latitude=data.latitude,
            longitude=data.longitude,
            customer_kind="unknown",
            status="quarantined",
            first_seen_at=now,
            last_seen_at=now,
        )
        self.session.add(business)
        self.session.flush()
        self.session.add(
            BusinessNicheMembershipModel(
                id=new_id("membership"),
                business_id=business.id,
                niche_id=segment.niche_id,
                market_key=data.market_key,
                confidence=1.0,
                evidence=[{"source": "admin", "source_url": data.source_url}],
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        source_value = SourceItemCreate(
            segment_id=segment.id,
            provider_id=data.source_provider,
            query=f"admin add {data.display_name}",
            source_url=normalize_url(data.source_url),
            title=data.display_name,
            raw_payload={
                "title": data.display_name,
                "url": normalize_url(data.source_url),
                "address": data.address,
                "geography": data.geography,
                "phone": data.phone,
                "website_url": normalize_url(data.website_url),
                "source": data.source_provider,
            },
            fetched_at=now,
        )
        source = SourceItemModel(
            id=new_id("source_item"),
            **source_value.model_dump(),
            content_hash=source_item_content_hash(source_value),
            state="validating",
            business_id=business.id,
        )
        self.session.add(source)
        self.session.flush()
        BusinessValidationService(self.session).validate(business=business, source_item=source, segment=segment)
        self._audit("create", business.id, data.reason, None, _business_dict(business))
        self.session.commit()
        return self.detail(business.id)

    def update(self, business_id: str, data: AdminBusinessUpdate) -> dict[str, Any]:
        business = self._business(business_id)
        before = _business_dict(business)
        updates = data.model_dump(exclude={"reason"}, exclude_unset=True)
        for field, value in updates.items():
            if field == "website_url":
                value = normalize_url(value)
                business.domain = normalize_domain(value)
            elif field == "phone":
                value = normalize_phone(value)
            elif field == "display_name" and value:
                value = value.strip()
                business.normalized_name = normalize_business_name(value)
            setattr(business, field, value)
        business.last_seen_at = utcnow()
        business.status = "quarantined"
        self._withdraw_publications(business.id, "quarantined")
        self._audit("update", business.id, data.reason, before, _business_dict(business))
        self.session.commit()
        return self.detail(business.id)

    def change_status(self, business_id: str, status: str, reason: str) -> dict[str, Any]:
        business = self._business(business_id)
        before = _business_dict(business)
        business.status = status
        if status != "active":
            self._withdraw_publications(business.id, status)
        self._audit(f"status:{status}", business.id, reason, before, _business_dict(business))
        self.session.commit()
        return self.detail(business.id)

    def revalidate(self, business_id: str, reason: str) -> dict[str, Any]:
        business = self._business(business_id)
        originals = list(
            self.session.scalars(select(SourceItemModel).where(SourceItemModel.business_id == business_id))
        )
        if not originals:
            raise ValidationError("This business has no source item to validate")
        original = min(
            originals,
            key=lambda item: (SOURCE_PRIORITY.get(item.provider_id, 99), -item.fetched_at.timestamp()),
        )
        segment = self.session.get(BusinessIndexSegmentModel, original.segment_id)
        if segment is None:
            raise ValidationError("The source item has no active segment")
        now = utcnow()
        source_value = SourceItemCreate(
            segment_id=original.segment_id,
            provider_id=original.provider_id,
            external_id=original.external_id,
            query=original.query,
            source_url=original.source_url,
            title=original.title,
            raw_payload=original.raw_payload,
            fetched_at=now,
        )
        source = SourceItemModel(
            id=new_id("source_item"),
            **source_value.model_dump(),
            content_hash=source_item_content_hash(source_value),
            state="validating",
            business_id=business_id,
        )
        self.session.add(source)
        self.session.flush()
        results = BusinessValidationService(self.session).validate(
            business=business, source_item=source, segment=segment
        )
        statuses = {result.status for result in results}
        source.state = "rejected" if "failed" in statuses else "needs_review" if statuses != {"passed"} else "validated"
        self._audit(
            "revalidate",
            business.id,
            reason,
            None,
            {"source_item_id": source.id, "results": {r.validation_type: r.status for r in results}},
        )
        self.session.commit()
        return self.detail(business.id)

    def delete_dependencies(self, business_id: str) -> dict[str, int]:
        self._business(business_id)
        dependencies: dict[str, int] = {}
        for table in Base.metadata.sorted_tables:
            if table.name in {"businesses", "admin_audit_events"}:
                continue
            columns = [
                column for column in table.columns
                if any(fk.column.table.name == "businesses" for fk in column.foreign_keys)
            ]
            if not columns:
                continue
            count = 0
            for column in columns:
                count += int(self.session.scalar(select(func.count()).select_from(table).where(column == business_id)) or 0)
            if count:
                dependencies[table.name] = count
        return dependencies

    def delete(self, business_id: str, confirmation: str, reason: str) -> None:
        business = self._business(business_id)
        if confirmation.strip() != business.display_name:
            raise ValidationError("Confirmation must exactly match the business name")
        dependencies = self.delete_dependencies(business_id)
        if dependencies:
            raise ConflictError(
                "Permanent deletion is blocked because related records exist. Archive the business instead.",
                {"dependencies": dependencies},
            )
        before = _business_dict(business)
        self._audit("delete", business.id, reason, before, None)
        self.session.delete(business)
        self.session.commit()

    def _business(self, business_id: str) -> BusinessModel:
        business = self.session.get(BusinessModel, business_id)
        if business is None:
            raise NotFoundError("business not found", {"business_id": business_id})
        return business

    def _validation_states(self, business_ids: list[str]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, ValidationResultModel]] = defaultdict(dict)
        if business_ids:
            rows = list(
                self.session.scalars(
                    select(ValidationResultModel)
                    .where(
                        ValidationResultModel.business_id.in_(business_ids),
                        ValidationResultModel.expires_at >= utcnow(),
                    )
                    .order_by(ValidationResultModel.observed_at.desc())
                )
            )
            for row in rows:
                grouped[row.business_id].setdefault(row.validation_type, row)
        result: dict[str, dict[str, Any]] = {}
        for business_id in business_ids:
            validations = grouped[business_id]
            required = {key: validations.get(key) for key in REQUIRED_VALIDATIONS}
            statuses = {row.status for row in required.values() if row is not None}
            state = (
                "incomplete"
                if any(row is None for row in required.values())
                else "passed"
                if statuses == {"passed"}
                else "attention"
            )
            result[business_id] = {
                "state": state,
                "validations": [
                    {
                        "id": row.id,
                        "type": row.validation_type,
                        "status": row.status,
                        "confidence": row.confidence,
                        "reason": row.reason,
                        "evidence": row.evidence,
                        "observed_at": row.observed_at,
                        "expires_at": row.expires_at,
                    }
                    for row in required.values()
                    if row is not None
                ],
            }
        return result

    def _business_summary(
        self,
        business: BusinessModel,
        state: dict[str, Any],
        membership=None,
    ) -> dict[str, Any]:
        return {
            "id": business.id,
            "display_name": business.display_name,
            "status": business.status,
            "validation_state": state["state"],
            "website_url": business.website_url,
            "domain": business.domain,
            "phone": business.phone,
            "address": business.address,
            "geography": business.geography,
            "market_key": membership[0].market_key if membership else business.market_key,
            "niche_slug": membership[1].slug if membership else business.category_key,
            "niche_label": membership[1].label if membership else business.category_key,
            "last_seen_at": business.last_seen_at,
        }

    def _primary_memberships(self, business_ids: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if not business_ids:
            return result
        rows = self.session.execute(
            select(BusinessNicheMembershipModel, NicheModel)
            .join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
            .where(BusinessNicheMembershipModel.business_id.in_(business_ids))
            .order_by(BusinessNicheMembershipModel.confidence.desc())
        )
        for membership, niche in rows:
            result.setdefault(membership.business_id, (membership, niche))
        return result

    def _withdraw_publications(self, business_id: str, status: str) -> None:
        for publication in self.session.scalars(
            select(BusinessPublicationModel).where(
                BusinessPublicationModel.business_id == business_id,
                BusinessPublicationModel.status == "published",
            )
        ):
            publication.status = status
            publication.reasons = [
                *(publication.reasons or []),
                {"code": "admin_withdrawal", "message": f"Business set to {status}."},
            ]
            publication.evaluated_at = utcnow()

    def _audit(
        self,
        action: str,
        entity_id: str,
        reason: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> None:
        self.session.add(
            AdminAuditEventModel(
                id=new_id("admin_audit"),
                actor_id=self.auth.user_id,
                actor_email=self.auth.email,
                action=action,
                entity_type="business",
                entity_id=entity_id,
                reason=reason,
                before=before,
                after=after,
            )
        )


def _business_dict(business: BusinessModel) -> dict[str, Any]:
    return {
        "display_name": business.display_name,
        "website_url": business.website_url,
        "domain": business.domain,
        "phone": business.phone,
        "address": business.address,
        "geography": business.geography,
        "market_key": business.market_key,
        "latitude": business.latitude,
        "longitude": business.longitude,
        "customer_kind": business.customer_kind,
        "is_chain": business.is_chain,
        "is_franchise": business.is_franchise,
        "is_directory": business.is_directory,
        "is_agency": business.is_agency,
        "status": business.status,
    }


def _fact_value(fact: BusinessFactModel) -> Any:
    if fact.value_type == "boolean":
        return fact.value_boolean
    if fact.value_type == "number":
        return fact.value_number
    return fact.value_text
