from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from business_facts.claims import FactClaim, FactClaimRepository
from business_facts.repository import BusinessFactRepository, BusinessFactValue
from canonical.repository import CanonicalRepository
from canonical.website_enrichment import BusinessWebsiteEnrichment, WebsiteEnrichmentClient
from db.models import (
    BusinessModel,
    FactClaimModel,
    SignalDefinitionModel,
    SourceObservationModel,
)
from shared.errors import ConflictError, NotFoundError
from shared.utils import utcnow


RESOLVER_VERSION = 1
WEBSITE_COLLECTORS = {"website_http", "website_dom"}
GOOGLE_SOURCES = {"google_places", "google_places_seed"}
DOMAIN_COLLECTORS = {"domain_rdap"}
PAGESPEED_COLLECTORS = {"pagespeed_mobile"}
PAGESPEED_SOURCE = "pagespeed_mobile"


class SignalCollectionService:
    def __init__(
        self,
        session: Session,
        *,
        timeout_seconds: float = 12.0,
        browser_render_endpoint: str | None = None,
        browser_render_api_key: str | None = None,
        pagespeed_api_key: str | None = None,
        pagespeed_api_endpoint: str = (
            "https://pagespeedonline.googleapis.com/pagespeedonline/v5/runPagespeed"
        ),
    ) -> None:
        self.session = session
        self.website = WebsiteEnrichmentClient(
            timeout_seconds=timeout_seconds,
            max_pages_per_business=5,
            page_delay_seconds=0,
            browser_render_endpoint=browser_render_endpoint,
            browser_render_api_key=browser_render_api_key,
        )
        self.pagespeed_api_key = pagespeed_api_key
        self.pagespeed_api_endpoint = pagespeed_api_endpoint

    def collect(
        self,
        signal_definition_id: str,
        *,
        expected_version: int,
        business_ids: list[str],
    ) -> dict[str, int]:
        definition = self.session.get(SignalDefinitionModel, signal_definition_id)
        if definition is None:
            raise NotFoundError(
                "signal definition not found",
                {"signal_definition_id": signal_definition_id},
            )
        if definition.status != "active":
            raise ConflictError("Signal definition is not active")
        if definition.version != expected_version:
            raise ConflictError(
                "Signal collection job uses an outdated definition version",
                {"expected": expected_version, "current": definition.version},
            )
        businesses = list(
            self.session.scalars(
                select(BusinessModel)
                .where(
                    BusinessModel.id.in_(business_ids),
                    BusinessModel.status != "archived",
                )
                .order_by(BusinessModel.id)
            )
        )
        summary = {"requested": len(business_ids), "observed": 0, "claimed": 0, "unknown": 0}
        for business in businesses:
            observation = self._observation(definition, business)
            if observation is None:
                summary["unknown"] += 1
                continue
            summary["observed"] += 1
            value = extract_signal_value(definition, observation.raw_payload or {})
            if value is None:
                summary["unknown"] += 1
                continue
            claim = FactClaimRepository(self.session).record(
                FactClaim(
                    business_id=business.id,
                    fact_key=definition.key,
                    value=value,
                    source_observation_id=observation.id,
                    confidence=int((definition.config or {}).get("confidence", 100)),
                    extractor=definition.extractor_key or "configured_extractor",
                    extractor_version=definition.version,
                    observed_at=observation.observed_at,
                    expires_at=observation.observed_at
                    + timedelta(days=definition.freshness_days),
                    signal_definition_id=definition.id,
                )
            )
            self._resolve(definition, business.id, claim)
            summary["claimed"] += 1
        self.session.commit()
        return summary

    def _observation(
        self,
        definition: SignalDefinitionModel,
        business: BusinessModel,
    ) -> SourceObservationModel | None:
        if definition.collector_key in WEBSITE_COLLECTORS:
            if definition.collector_key == "website_dom" and not business.website_url:
                return None
            existing = self._recent_observation(
                business.id,
                sources={"company_website_signal"},
                freshness_days=definition.freshness_days,
            )
            if existing is not None and _extract_value(
                definition, existing.raw_payload or {}
            ) is not None:
                return existing
            enrichment = self.website.inspect(business)
            raw = _website_payload(business, definition, enrichment)
            link = CanonicalRepository(self.session).record_business_evidence(
                business=business,
                source="company_website_signal",
                raw=raw,
                contact_email=enrichment.best_email,
            )
            return self.session.get(SourceObservationModel, link.source_observation_id)
        if definition.collector_key in PAGESPEED_COLLECTORS:
            return self._pagespeed_observation(definition, business)
        if definition.collector_key in DOMAIN_COLLECTORS:
            return self._domain_observation(definition, business)
        statement = select(SourceObservationModel).where(
            SourceObservationModel.business_id == business.id
        )
        if definition.collector_key == "google_places":
            statement = statement.where(SourceObservationModel.source.in_(GOOGLE_SOURCES))
        return self.session.scalar(
            statement.order_by(SourceObservationModel.observed_at.desc()).limit(1)
        )

    def _recent_observation(
        self,
        business_id: str,
        *,
        sources: set[str],
        freshness_days: int,
    ) -> SourceObservationModel | None:
        return self.session.scalar(
            select(SourceObservationModel)
            .where(
                SourceObservationModel.business_id == business_id,
                SourceObservationModel.source.in_(sources),
                SourceObservationModel.observed_at
                >= utcnow() - timedelta(days=freshness_days),
            )
            .order_by(SourceObservationModel.observed_at.desc())
            .limit(1)
        )

    def _pagespeed_observation(
        self,
        definition: SignalDefinitionModel,
        business: BusinessModel,
    ) -> SourceObservationModel | None:
        existing = self._recent_observation(
            business.id,
            sources={PAGESPEED_SOURCE},
            freshness_days=definition.freshness_days,
        )
        if existing is not None:
            error = _payload_path(existing.raw_payload or {}, "pagespeed_mobile.error")
            if error is None or existing.observed_at >= utcnow() - timedelta(days=1):
                return existing
        if not business.website_url:
            return None
        params: list[tuple[str, str]] = [
            ("url", business.website_url),
            ("strategy", "mobile"),
            ("category", "performance"),
            ("category", "accessibility"),
            ("category", "best-practices"),
            ("category", "seo"),
        ]
        if self.pagespeed_api_key:
            params.append(("key", self.pagespeed_api_key))
        try:
            response = httpx.get(
                self.pagespeed_api_endpoint,
                params=params,
                timeout=max(self.website.timeout_seconds, 60),
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return self._record_pagespeed_observation(
                definition,
                business,
                {"error": str(exc), "website_url": business.website_url},
            )
        normalized = _normalized_pagespeed_payload(payload)
        if normalized is None:
            return self._record_pagespeed_observation(
                definition,
                business,
                {
                    "error": "PageSpeed response did not contain a usable Lighthouse result.",
                    "website_url": business.website_url,
                },
            )
        return self._record_pagespeed_observation(definition, business, normalized)

    def _record_pagespeed_observation(
        self,
        definition: SignalDefinitionModel,
        business: BusinessModel,
        normalized: dict[str, Any],
    ) -> SourceObservationModel:
        raw = {
            "company_name": business.display_name,
            "website_url": business.website_url,
            "source": PAGESPEED_SOURCE,
            "source_url": business.website_url,
            "external_id": f"pagespeed:{business.id}",
            "signal_collection": {
                "signal_definition_id": definition.id,
                "signal_key": definition.key,
                "signal_version": definition.version,
                "collector_key": definition.collector_key,
            },
            "pagespeed_mobile": normalized,
        }
        link = CanonicalRepository(self.session).record_business_evidence(
            business=business,
            source=PAGESPEED_SOURCE,
            raw=raw,
        )
        return self.session.get(SourceObservationModel, link.source_observation_id)

    def _domain_observation(
        self,
        definition: SignalDefinitionModel,
        business: BusinessModel,
    ) -> SourceObservationModel | None:
        domain = _business_domain(business)
        if not domain:
            return None
        try:
            response = httpx.get(
                f"https://rdap.org/domain/{domain}",
                timeout=self.website.timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        registered_at = _rdap_registration_date(payload)
        age_days = (
            max(0, (utcnow() - registered_at).days)
            if registered_at is not None
            else None
        )
        raw = {
            "company_name": business.display_name,
            "website_url": business.website_url,
            "source": "domain_rdap",
            "source_url": f"https://rdap.org/domain/{domain}",
            "external_id": f"rdap:{domain}",
            "signal_collection": {
                "signal_definition_id": definition.id,
                "signal_key": definition.key,
                "signal_version": definition.version,
                "collector_key": definition.collector_key,
            },
            "domain_rdap": {
                "domain": domain,
                "registered_at": registered_at.isoformat() if registered_at else None,
                "age_days": age_days,
            },
        }
        link = CanonicalRepository(self.session).record_business_evidence(
            business=business,
            source="domain_rdap",
            raw=raw,
        )
        return self.session.get(SourceObservationModel, link.source_observation_id)

    def _resolve(
        self,
        definition: SignalDefinitionModel,
        business_id: str,
        newest: FactClaimModel,
    ) -> None:
        claims = list(
            self.session.scalars(
                select(FactClaimModel)
                .where(
                    FactClaimModel.business_id == business_id,
                    FactClaimModel.signal_definition_id == definition.id,
                    FactClaimModel.expires_at >= newest.observed_at,
                )
                .order_by(FactClaimModel.observed_at.desc(), FactClaimModel.confidence.desc())
            )
        )
        supporting = tuple(claim.id for claim in claims if claim.value == newest.value)
        conflicting = any(
            claim.value != newest.value and claim.confidence >= 90 for claim in claims
        )
        config = definition.config or {}
        requires_validation = bool(config.get("requires_validation", True))
        quality_state = (
            "published"
            if not requires_validation and bool(config.get("auto_publish"))
            else "staged"
        )
        BusinessFactRepository(self.session).upsert(
            business_id,
            BusinessFactValue(
                key=definition.key,
                value=newest.value,
                observed_at=newest.observed_at,
                source_observation_id=newest.source_observation_id,
                confidence=newest.confidence,
                resolution_state="conflicted" if conflicting else "confirmed",
                supporting_claim_ids=supporting,
                quality_state=quality_state,
                expires_at=newest.expires_at,
                resolver_version=RESOLVER_VERSION,
            ),
        )


def _website_payload(
    business: BusinessModel,
    definition: SignalDefinitionModel,
    enrichment: BusinessWebsiteEnrichment,
) -> dict[str, Any]:
    return {
        "company_name": business.display_name,
        "website_url": business.website_url,
        "source": "company_website_signal",
        "source_url": enrichment.source_url or business.website_url,
        "external_id": f"signal:{definition.id}:{business.id}",
        "query": f"collect {definition.key} for {business.display_name}",
        "signal_collection": {
            "signal_definition_id": definition.id,
            "signal_key": definition.key,
            "signal_version": definition.version,
            "collector_key": definition.collector_key,
        },
        "website_enrichment": {
            "inspected_urls": enrichment.inspected_urls,
            "availability_status": enrichment.availability_status,
            "availability_reason": enrichment.availability_reason,
            "has_contact_form": enrichment.has_contact_form,
            "has_quote_form": enrichment.has_quote_form,
            "has_booking_form": enrichment.has_booking_form,
            "uses_https": enrichment.uses_https,
            "has_mobile_viewport": enrichment.has_mobile_viewport,
            **enrichment.page_signals,
            "quote_signals": enrichment.quote_signals,
            "service_signals": enrichment.service_signals,
            "errors": enrichment.errors[:5],
        },
    }


def _extract_value(definition: SignalDefinitionModel, payload: dict[str, Any]) -> Any | None:
    configured_path = str((definition.config or {}).get("payload_path") or "").strip()
    if configured_path:
        return _payload_path(payload, configured_path)
    enrichment = payload.get("website_enrichment")
    if not isinstance(enrichment, dict):
        enrichment = {}
    extractors = {
        "website_status": lambda: _website_status(enrichment),
        "contact_form": lambda: enrichment.get("has_contact_form"),
        "quote_or_booking_form": lambda: _combined_boolean(
            enrichment.get("has_quote_form"), enrichment.get("has_booking_form")
        ),
        "google_rating": lambda: _first_value(payload, {"google_rating", "rating"}),
        "google_review_count": lambda: _first_value(
            payload, {"google_review_count", "userRatingCount", "review_count"}
        ),
        "business_operational": lambda: _operational_value(payload),
        "domain_age_days": lambda: _payload_path(payload, "domain_rdap.age_days"),
        "uses_https": lambda: enrichment.get("uses_https"),
        "mobile_viewport": lambda: enrichment.get("has_mobile_viewport"),
        "primary_cta": lambda: enrichment.get("has_primary_cta"),
        "click_to_call": lambda: enrichment.get("has_click_to_call"),
        "online_payment_or_financing": lambda: enrichment.get(
            "has_online_payment_or_financing"
        ),
        "service_area_pages": lambda: enrichment.get("has_service_area_pages"),
        "testimonials": lambda: enrichment.get("has_testimonials"),
        "privacy_policy": lambda: enrichment.get("has_privacy_policy"),
        "complete_contact_details": lambda: enrichment.get(
            "has_complete_contact_details"
        ),
        "html_language_present": lambda: enrichment.get("html_language_present"),
        "hreflang_present": lambda: enrichment.get("hreflang_present"),
        "language_selector_present": lambda: enrichment.get(
            "language_selector_present"
        ),
        "translated_page_count": lambda: enrichment.get("translated_page_count"),
        "market_language_supported": lambda: enrichment.get(
            "market_language_supported"
        ),
        "pagespeed_performance_score": lambda: _payload_path(
            payload, "pagespeed_mobile.performance_score"
        ),
        "pagespeed_accessibility_score": lambda: _payload_path(
            payload, "pagespeed_mobile.accessibility_score"
        ),
        "pagespeed_best_practices_score": lambda: _payload_path(
            payload, "pagespeed_mobile.best_practices_score"
        ),
        "pagespeed_seo_score": lambda: _payload_path(
            payload, "pagespeed_mobile.seo_score"
        ),
        "pagespeed_quality_score": lambda: _payload_path(
            payload, "pagespeed_mobile.website_quality_score"
        ),
        "pagespeed_lcp_ms": lambda: _payload_path(payload, "pagespeed_mobile.lcp_ms"),
        "pagespeed_cls": lambda: _payload_path(payload, "pagespeed_mobile.cls"),
        "pagespeed_inp_ms": lambda: _payload_path(payload, "pagespeed_mobile.inp_ms"),
        "pagespeed_tbt_ms": lambda: _payload_path(payload, "pagespeed_mobile.tbt_ms"),
    }
    extractor = extractors.get(definition.extractor_key or "")
    return extractor() if extractor else None


def extract_signal_value(
    definition: SignalDefinitionModel,
    payload: dict[str, Any],
) -> str | float | bool | None:
    return _coerce_value(
        definition.value_type,
        _extract_value(definition, payload),
    )


def _coerce_value(value_type: str, value: Any) -> str | float | bool | None:
    if value is None:
        return None
    if value_type == "boolean":
        return value if isinstance(value, bool) else None
    if value_type == "number":
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).strip())
        except ValueError:
            return None
    if value_type == "text":
        return value if isinstance(value, str) and value.strip() else None
    return None


def _website_status(enrichment: dict[str, Any]) -> str | None:
    status = str(enrichment.get("availability_status") or "").strip().lower()
    return {
        "active": "present",
        "available": "present",
        "missing": "missing",
        "unavailable": "unavailable",
        "parked": "parked",
        "inconclusive": "unknown",
    }.get(status)


def _combined_boolean(*values: Any) -> bool | None:
    present = [value for value in values if isinstance(value, bool)]
    return any(present) if present else None


def _payload_path(payload: dict[str, Any], path: str) -> Any | None:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value if value not in (None, "", [], {}) else None


def _first_value(value: Any, keys: set[str]) -> Any | None:
    if isinstance(value, dict):
        for key, entry in value.items():
            if key in keys and entry not in (None, "", [], {}):
                return entry
        for entry in value.values():
            found = _first_value(entry, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for entry in value:
            found = _first_value(entry, keys)
            if found is not None:
                return found
    return None


def _business_domain(business: BusinessModel) -> str | None:
    candidate = business.domain or business.website_url
    if not candidate:
        return None
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    return parsed.hostname.lower().removeprefix("www.") if parsed.hostname else None


def _rdap_registration_date(payload: Any) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    for event in payload.get("events") or []:
        if not isinstance(event, dict) or event.get("eventAction") != "registration":
            continue
        raw = str(event.get("eventDate") or "").strip().replace("Z", "+00:00")
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def _operational_value(payload: dict[str, Any]) -> bool | None:
    value = _first_value(payload, {"businessStatus"})
    normalized = str(value or "").strip().upper()
    if normalized == "OPERATIONAL":
        return True
    if normalized in {"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"}:
        return False
    return None


def _normalized_pagespeed_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    lighthouse = payload.get("lighthouseResult")
    if not isinstance(lighthouse, dict) or lighthouse.get("runtimeError"):
        return None
    categories = lighthouse.get("categories")
    audits = lighthouse.get("audits")
    if not isinstance(categories, dict) or not isinstance(audits, dict):
        return None

    def category_score(key: str) -> float | None:
        category = categories.get(key)
        score = category.get("score") if isinstance(category, dict) else None
        return round(float(score) * 100, 1) if isinstance(score, (int, float)) else None

    def audit_value(key: str) -> float | None:
        audit = audits.get(key)
        value = audit.get("numericValue") if isinstance(audit, dict) else None
        return round(float(value), 3) if isinstance(value, (int, float)) else None

    scores = {
        "performance_score": category_score("performance"),
        "accessibility_score": category_score("accessibility"),
        "best_practices_score": category_score("best-practices"),
        "seo_score": category_score("seo"),
    }
    available_scores = [value for value in scores.values() if value is not None]
    loading_experience = payload.get("loadingExperience")
    metrics = (
        loading_experience.get("metrics")
        if isinstance(loading_experience, dict)
        else None
    )
    inp = (
        metrics.get("INTERACTION_TO_NEXT_PAINT")
        or metrics.get("INTERACTION_TO_NEXT_PAINT_MS")
        if isinstance(metrics, dict)
        else None
    )
    inp_percentile = inp.get("percentile") if isinstance(inp, dict) else None
    return {
        **scores,
        "website_quality_score": (
            round(sum(available_scores) / len(available_scores), 1)
            if available_scores
            else None
        ),
        "lcp_ms": audit_value("largest-contentful-paint"),
        "cls": audit_value("cumulative-layout-shift"),
        "tbt_ms": audit_value("total-blocking-time"),
        "inp_ms": (
            float(inp_percentile)
            if isinstance(inp_percentile, (int, float))
            else None
        ),
        "final_url": lighthouse.get("finalUrl") or payload.get("id"),
        "lighthouse_version": lighthouse.get("lighthouseVersion"),
        "analyzed_at": payload.get("analysisUTCTimestamp") or lighthouse.get("fetchTime"),
        "warnings": list(lighthouse.get("runWarnings") or [])[:10],
    }
