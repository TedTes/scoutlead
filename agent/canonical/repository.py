from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from agents.embeddings import EmbeddingClient, MissingEmbeddingClient
from canonical.normalization import (
    contact_name_from_raw,
    email_from_raw,
    external_id_from_raw,
    iter_raw_layers,
    normalize_business_name,
    normalize_domain,
    normalize_email,
    normalize_phone,
    phone_from_raw,
    query_from_source_input,
    query_signature,
    source_input_signature,
    source_url_from_raw,
    stable_content_hash,
)
from canonical.semantics import (
    business_semantic_profile,
    cosine_similarity,
    market_is_compatible,
    request_semantic_profile,
    semantic_key,
)
from db.models import BusinessModel, ContactModel, SourceObservationModel
from shared.utils import new_id, normalize_text, normalize_url, utcnow


@dataclass(frozen=True)
class CanonicalLeadLink:
    business_id: str | None
    contact_id: str | None


class CanonicalRepository:
    def __init__(self, session: Session, *, embedding: EmbeddingClient | None = None) -> None:
        self.session = session
        self.embedding = embedding or MissingEmbeddingClient()

    def upsert_from_discovery_result(
        self,
        *,
        company_name: str,
        website_url: str | None = None,
        contact_email: str | None = None,
        geography: str | None = None,
        description: str | None = None,
        source: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> CanonicalLeadLink:
        raw_payload = raw or {}
        source_name = normalize_text(source) or "unknown"
        business = self._upsert_business(
            company_name=company_name,
            website_url=website_url,
            geography=geography,
            description=description,
            source=source_name,
            raw=raw_payload,
        )
        contact = self._upsert_contact(
            business=business,
            email=contact_email,
            raw=raw_payload,
        )
        self._record_source_observation(
            business=business,
            source=source_name,
            query=_query_from_raw(raw_payload),
            raw=raw_payload
            or {
                "company_name": company_name,
                "website_url": website_url,
                "contact_email": contact_email,
                "geography": geography,
                "description": description,
                "source": source_name,
            },
        )
        self.session.flush()
        return CanonicalLeadLink(
            business_id=business.id,
            contact_id=contact.id if contact else None,
        )

    def list_cached_discovery_results(
        self,
        *,
        source: str,
        source_input: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        signature = source_input_signature(source=source, source_input=source_input)
        if not signature:
            return []
        statement = (
            select(SourceObservationModel, BusinessModel)
            .join(BusinessModel, BusinessModel.id == SourceObservationModel.business_id)
            .where(
                SourceObservationModel.source == source,
                SourceObservationModel.query_signature == signature,
            )
            .order_by(SourceObservationModel.observed_at.desc())
            .limit(limit)
        )
        rows: list[dict[str, Any]] = []
        seen_business_ids: set[str] = set()
        for observation, business in self.session.execute(statement).all():
            if business.id in seen_business_ids:
                continue
            seen_business_ids.add(business.id)
            rows.append(_observation_to_search_result(observation, business))
        return rows

    def list_semantic_discovery_results(
        self,
        *,
        source_inputs: dict[str, Any],
        source_input: str | None,
        limit: int,
        min_score: float,
        min_results: int,
    ) -> list[dict[str, Any]]:
        if limit <= 0 or min_results <= 0:
            return []

        profile = request_semantic_profile(
            source_inputs=source_inputs,
            source_input=source_input,
        )
        if not profile.text:
            return []

        self._backfill_semantic_fields(
            request_market_key=profile.market_key,
            limit=max(limit * 20, 200),
        )
        query_embedding = self.embedding.embed_text(profile.text)
        if query_embedding:
            matches = self._embedding_matches(
                query_embedding=query_embedding,
                market_key=profile.market_key,
                limit=limit,
                min_score=min_score,
            )
        else:
            matches = self._structured_matches(
                category_key=profile.category_key,
                market_key=profile.market_key,
                limit=limit,
            )

        if len(matches) < min_results:
            return []

        rows: list[dict[str, Any]] = []
        for score, business in matches[:limit]:
            observation = self._latest_observation_for_business(business.id)
            row = (
                _observation_to_search_result(observation, business)
                if observation is not None
                else _business_to_search_result(business)
            )
            raw = dict(row.get("raw") or {})
            raw["semantic_cache_hit"] = True
            raw["semantic_similarity"] = round(score, 4)
            raw["semantic_request"] = {
                "category_key": profile.category_key,
                "market_key": profile.market_key,
                "text": profile.text,
            }
            row["raw"] = raw
            rows.append(row)
        return rows

    def apply_contact_verification(
        self,
        *,
        contact_id: str | None,
        status: str,
        provider: str | None,
        checked_at,
        reason: str | None,
        score: int | None,
        details: dict[str, Any] | None,
    ) -> None:
        if not contact_id:
            return
        contact = self.session.get(ContactModel, contact_id)
        if contact is None:
            return
        contact.verification_status = status
        contact.verification_provider = provider
        contact.verification_checked_at = checked_at
        contact.verification_reason = reason
        contact.verification_score = score
        contact.verification_details = details
        contact.last_seen_at = utcnow()
        self.session.flush()

    def _upsert_business(
        self,
        *,
        company_name: str,
        website_url: str | None,
        geography: str | None,
        description: str | None,
        source: str,
        raw: dict[str, Any],
    ) -> BusinessModel:
        now = utcnow()
        display_name = normalize_text(company_name)
        normalized_name = normalize_business_name(display_name)
        normalized_url = normalize_url(website_url) or source_url_from_raw(raw)
        domain = normalize_domain(normalized_url)
        normalized_geography = normalize_text(geography) or None
        phone = phone_from_raw(raw)
        profile = business_semantic_profile(
            company_name=display_name,
            website_url=normalized_url,
            geography=normalized_geography,
            description=description,
            source=source,
            raw=raw,
        )

        business = self._find_business(
            source=source,
            external_id=external_id_from_raw(raw),
            normalized_name=normalized_name,
            domain=domain,
            geography=normalized_geography,
        )
        if business is None:
            business = BusinessModel(
                id=new_id("business"),
                display_name=display_name,
                normalized_name=normalized_name,
                website_url=normalized_url,
                domain=domain,
                phone=phone,
                address=_address_from_raw(raw) or normalized_geography,
                geography=normalized_geography,
                category_key=profile.category_key,
                market_key=profile.market_key,
                semantic_text=profile.text,
                first_seen_at=now,
                last_seen_at=now,
            )
            self._refresh_embedding_if_needed(business, profile.text, now=now)
            self.session.add(business)
            self.session.flush()
            return business

        business.display_name = _prefer_existing(business.display_name, display_name)
        business.normalized_name = business.normalized_name or normalized_name
        business.website_url = business.website_url or normalized_url
        business.domain = business.domain or domain
        business.phone = business.phone or phone
        business.address = business.address or _address_from_raw(raw) or normalized_geography
        business.geography = business.geography or normalized_geography
        business.category_key = business.category_key or profile.category_key
        business.market_key = business.market_key or profile.market_key
        if profile.text:
            previous_semantic_text = business.semantic_text
            business.semantic_text = profile.text
            if (
                not business.embedding
                or previous_semantic_text != profile.text
                or business.embedding_model != self.embedding.model
            ):
                self._refresh_embedding_if_needed(business, profile.text, now=now)
        business.last_seen_at = now
        self.session.flush()
        return business

    def _find_business(
        self,
        *,
        source: str,
        external_id: str | None,
        normalized_name: str,
        domain: str | None,
        geography: str | None,
    ) -> BusinessModel | None:
        if external_id:
            observation = self.session.scalar(
                select(SourceObservationModel)
                .where(
                    SourceObservationModel.source == source,
                    SourceObservationModel.external_id == external_id,
                )
                .order_by(SourceObservationModel.observed_at.desc())
                .limit(1)
            )
            if observation:
                return observation.business

        if domain:
            business = self.session.scalar(
                select(BusinessModel)
                .where(BusinessModel.domain == domain)
                .order_by(BusinessModel.created_at)
                .limit(1)
            )
            if business:
                return business

        if normalized_name and geography:
            business = self.session.scalar(
                select(BusinessModel)
                .where(
                    BusinessModel.normalized_name == normalized_name,
                    BusinessModel.geography == geography,
                )
                .order_by(BusinessModel.created_at)
                .limit(1)
            )
            if business:
                return business

        if normalized_name:
            return self.session.scalar(
                select(BusinessModel)
                .where(BusinessModel.normalized_name == normalized_name)
                .order_by(BusinessModel.created_at)
                .limit(1)
            )
        return None

    def _upsert_contact(
        self,
        *,
        business: BusinessModel,
        email: str | None,
        raw: dict[str, Any],
    ) -> ContactModel | None:
        normalized_email = normalize_email(email) or email_from_raw(raw)
        phone = phone_from_raw(raw)
        name = contact_name_from_raw(raw)
        if not any([normalized_email, phone, name]):
            return None

        now = utcnow()
        contact = self._find_contact(business_id=business.id, email=normalized_email, phone=phone)
        if contact is None:
            contact = ContactModel(
                id=new_id("contact"),
                business_id=business.id,
                name=name,
                role=_role_from_raw(raw),
                email=normalized_email,
                phone=phone,
                verification_status="unverified",
                first_seen_at=now,
                last_seen_at=now,
            )
            self.session.add(contact)
            self.session.flush()
            return contact

        contact.name = contact.name or name
        contact.role = contact.role or _role_from_raw(raw)
        contact.email = contact.email or normalized_email
        contact.phone = contact.phone or phone
        contact.last_seen_at = now
        self.session.flush()
        return contact

    def _find_contact(
        self,
        *,
        business_id: str,
        email: str | None,
        phone: str | None,
    ) -> ContactModel | None:
        if email:
            contact = self.session.scalar(
                select(ContactModel)
                .where(ContactModel.business_id == business_id, ContactModel.email == email)
                .order_by(ContactModel.created_at)
                .limit(1)
            )
            if contact:
                return contact
        if phone:
            return self.session.scalar(
                select(ContactModel)
                .where(ContactModel.business_id == business_id, ContactModel.phone == phone)
                .order_by(ContactModel.created_at)
                .limit(1)
            )
        return None

    def _record_source_observation(
        self,
        *,
        business: BusinessModel,
        source: str,
        query: str | None,
        raw: dict[str, Any],
    ) -> SourceObservationModel:
        now = utcnow()
        external_id = external_id_from_raw(raw)
        signature = query_signature(source=source, query=query)
        content_hash = stable_content_hash(raw)

        observation = None
        if external_id:
            observation = self.session.scalar(
                select(SourceObservationModel)
                .where(
                    SourceObservationModel.source == source,
                    SourceObservationModel.external_id == external_id,
                )
                .limit(1)
            )
        if observation is None:
            observation = self.session.scalar(
                select(SourceObservationModel)
                .where(
                    SourceObservationModel.source == source,
                    SourceObservationModel.content_hash == content_hash,
                )
                .limit(1)
            )
        if observation is None:
            observation = SourceObservationModel(
                id=new_id("sourceobs"),
                business_id=business.id,
                source=source,
                external_id=external_id,
                query_signature=signature,
                content_hash=content_hash,
                source_url=source_url_from_raw(raw),
                raw_payload=raw,
                observed_at=now,
            )
            self.session.add(observation)
            self.session.flush()
            return observation

        observation.business_id = business.id
        observation.query_signature = observation.query_signature or signature
        observation.source_url = observation.source_url or source_url_from_raw(raw)
        observation.raw_payload = raw
        observation.observed_at = now
        self.session.flush()
        return observation

    def _embedding_matches(
        self,
        *,
        query_embedding: list[float],
        market_key: str | None,
        limit: int,
        min_score: float,
    ) -> list[tuple[float, BusinessModel]]:
        statement = (
            select(BusinessModel)
            .where(BusinessModel.embedding.is_not(None))
            .order_by(BusinessModel.last_seen_at.desc())
            .limit(max(limit * 20, 200))
        )
        matches: list[tuple[float, BusinessModel]] = []
        for business in self.session.scalars(statement):
            if not market_is_compatible(market_key, business.market_key):
                continue
            score = cosine_similarity(query_embedding, business.embedding)
            if score >= min_score:
                matches.append((score, business))
        matches.sort(key=lambda item: (item[0], item[1].last_seen_at), reverse=True)
        return matches[:limit]

    def _structured_matches(
        self,
        *,
        category_key: str | None,
        market_key: str | None,
        limit: int,
    ) -> list[tuple[float, BusinessModel]]:
        if not category_key and not market_key:
            return []
        statement = select(BusinessModel)
        if category_key:
            statement = statement.where(BusinessModel.category_key == category_key)
        if market_key:
            statement = statement.where(BusinessModel.market_key == market_key)
        statement = statement.order_by(BusinessModel.last_seen_at.desc()).limit(limit)
        return [(1.0, business) for business in self.session.scalars(statement)]

    def _latest_observation_for_business(self, business_id: str) -> SourceObservationModel | None:
        return self.session.scalar(
            select(SourceObservationModel)
            .where(SourceObservationModel.business_id == business_id)
            .order_by(SourceObservationModel.observed_at.desc())
            .limit(1)
        )

    def _backfill_semantic_fields(
        self,
        *,
        request_market_key: str | None,
        limit: int,
    ) -> None:
        statement = (
            select(BusinessModel)
            .where(or_(BusinessModel.semantic_text.is_(None), BusinessModel.embedding.is_(None)))
            .order_by(BusinessModel.last_seen_at.desc())
            .limit(limit)
        )
        now = utcnow()
        changed = False
        for business in self.session.scalars(statement):
            business_market_key = business.market_key or semantic_key(business.geography)
            if not market_is_compatible(request_market_key, business_market_key):
                continue
            observation = self._latest_observation_for_business(business.id)
            raw = observation.raw_payload if observation is not None else {}
            profile = business_semantic_profile(
                company_name=business.display_name,
                website_url=business.website_url,
                geography=business.geography,
                description=_description_from_raw(raw) or business.semantic_text,
                source=observation.source if observation is not None else "canonical_cache",
                raw=raw,
            )
            previous_semantic_text = business.semantic_text
            business.category_key = business.category_key or profile.category_key
            business.market_key = business.market_key or profile.market_key
            if profile.text:
                business.semantic_text = profile.text
                changed = True
                if (
                    not business.embedding
                    or previous_semantic_text != profile.text
                    or business.embedding_model != self.embedding.model
                ):
                    self._refresh_embedding_if_needed(business, profile.text, now=now)
        if changed:
            self.session.flush()

    def _refresh_embedding_if_needed(
        self,
        business: BusinessModel,
        semantic_text: str,
        *,
        now,
    ) -> None:
        if not semantic_text:
            return
        embedding = self.embedding.embed_text(semantic_text)
        if not embedding:
            return
        business.embedding = embedding
        business.embedding_model = self.embedding.model
        business.embedding_updated_at = now


def _query_from_raw(raw: dict[str, Any]) -> str | None:
    for layer in iter_raw_layers(raw):
        source_input = layer.get("source_input")
        if isinstance(source_input, dict):
            query = query_from_source_input(source_input)
            if query:
                return query
    for layer in iter_raw_layers(raw):
        for key in ("discovery_query", "query", "search_query"):
            value = layer.get(key)
            if isinstance(value, str) and value.strip():
                geography = layer.get("discovery_geography")
                if (
                    isinstance(geography, str)
                    and geography.strip()
                    and geography.lower() not in value.lower()
                ):
                    return f"{normalize_text(value)} {normalize_text(geography)}"
                return normalize_text(value)
    return None


def _address_from_raw(raw: dict[str, Any]) -> str | None:
    for layer in iter_raw_layers(raw):
        for key in ("formattedAddress", "address", "fullAddress", "location"):
            value = layer.get(key)
            if isinstance(value, str) and value.strip():
                return normalize_text(value)
    return None


def _description_from_raw(raw: dict[str, Any]) -> str | None:
    for layer in iter_raw_layers(raw):
        for key in ("snippet", "description", "summary", "editorialSummary"):
            value = layer.get(key)
            if isinstance(value, str) and value.strip():
                return normalize_text(value)
            if isinstance(value, dict):
                text = value.get("text")
                if isinstance(text, str) and text.strip():
                    return normalize_text(text)
    return None


def _role_from_raw(raw: dict[str, Any]) -> str | None:
    for layer in iter_raw_layers(raw):
        for key in ("contact_role", "contactRole", "role", "job_title", "jobTitle"):
            value = layer.get(key)
            if isinstance(value, str) and value.strip():
                return normalize_text(value)
    return None


def _prefer_existing(existing: str | None, candidate: str | None) -> str:
    if existing and existing.strip():
        return existing
    return candidate or ""


def _observation_to_search_result(
    observation: SourceObservationModel,
    business: BusinessModel,
) -> dict[str, Any]:
    raw = observation.raw_payload or {}
    nested = raw.get("raw") if isinstance(raw.get("raw"), dict) else {}
    title = (
        _first_cached_text(raw, nested, ("title", "company_name", "name"))
        or business.display_name
    )
    url = (
        _first_cached_text(
            raw,
            nested,
            ("url", "website_url", "websiteUri", "google_maps_url", "googleMapsUri"),
        )
        or business.website_url
    )
    snippet = _first_cached_text(raw, nested, ("snippet", "description", "summary"))
    geography = (
        _first_cached_text(raw, nested, ("geography", "formattedAddress", "address"))
        or business.geography
    )
    contact_email = _first_cached_text(raw, nested, ("contact_email", "contactEmail", "email"))
    contact_email = contact_email or _first_contact_email(business)
    result_source = _first_cached_text(raw, nested, ("source",)) or observation.source
    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "geography": geography,
        "contact_email": contact_email,
        "source": result_source,
        "raw": {
            **raw,
            "cache_hit": True,
            "canonical_business_id": business.id,
            "source_observation_id": observation.id,
        },
    }


def _business_to_search_result(business: BusinessModel) -> dict[str, Any]:
    return {
        "title": business.display_name,
        "url": business.website_url,
        "snippet": business.semantic_text,
        "geography": business.geography,
        "contact_email": _first_contact_email(business),
        "source": "canonical_cache",
        "raw": {
            "cache_hit": True,
            "canonical_business_id": business.id,
        },
    }


def _first_contact_email(business: BusinessModel) -> str | None:
    for contact in business.contacts:
        if contact.email:
            return contact.email
    return None


def _first_cached_text(
    raw: dict[str, Any],
    nested: dict[str, Any],
    keys: tuple[str, ...],
) -> str | None:
    for source in (raw, nested):
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return normalize_text(value)
            if isinstance(value, (int, float)):
                return str(value)
    return None
