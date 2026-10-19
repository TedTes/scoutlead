from __future__ import annotations

from datetime import timedelta
import json
import math
import re
from urllib.parse import urlparse
from types import SimpleNamespace

from sqlalchemy.orm import Session

from db.models import (
    BusinessIndexSegmentModel,
    BusinessModel,
    SourceItemModel,
    SourceObservationModel,
)
from business_validation.repository import ValidationRepository, ValidationResult
from niches.catalog import NICHE_BY_SLUG
from shared.utils import utcnow
from territories.markets import market_center, market_matches_location


VALIDATOR_VERSION = 2
BLOCKED_HOSTS = {
    "angi.com",
    "bbb.org",
    "kijiji.ca",
    "craigslist.org",
    "facebook.com",
    "homestars.com",
    "houzz.com",
    "mapquest.com",
    "thumbtack.com",
    "trustedpros.ca",
    "yelp.ca",
    "yelp.com",
    "yellowpages.ca",
}
GENERIC_TITLES = {
    "renovation",
    "professional painter for hire",
    "home painting wall renovation services",
    "professional toronto house painters",
}
GENERIC_TRADE_TERMS = {
    "business",
    "businesses",
    "company",
    "contractor",
    "contractors",
    "home",
    "independent",
    "local",
    "provider",
    "providers",
    "residential",
    "service",
    "services",
}
TRADE_TERMS = {
    slug: set(spec.trade_terms) for slug, spec in NICHE_BY_SLUG.items()
}


class BusinessValidationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.results = ValidationRepository(session)

    def validate(
        self,
        *,
        business: BusinessModel,
        source_item: SourceItemModel,
        segment: BusinessIndexSegmentModel,
    ) -> list:
        candidates = self.evaluate(
            business=business,
            source_item=source_item,
            segment=segment,
        )
        return self.record(candidates)

    def record(
        self,
        candidates: list[ValidationResult],
        *,
        commit: bool = True,
    ) -> list:
        models = [self.results.record(result) for result in candidates]
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return models

    def evaluate(
        self,
        *,
        business: BusinessModel,
        source_item: SourceItemModel,
        segment: BusinessIndexSegmentModel,
    ) -> list[ValidationResult]:
        now = utcnow()
        expires_at = now + timedelta(days=30)
        return [
            self._identity(business, source_item, now, expires_at),
            self._business_type(business, source_item, now, expires_at),
            self._trade(business, source_item, segment, now, expires_at),
            self._location(business, source_item, segment, now, expires_at),
        ]

    def validate_observation(
        self,
        *,
        business: BusinessModel,
        observation: SourceObservationModel,
        segment: BusinessIndexSegmentModel,
    ) -> list:
        candidates = self.evaluate_observation(
            business=business,
            observation=observation,
            segment=segment,
        )
        return self.record(candidates)

    def evaluate_observation(
        self,
        *,
        business: BusinessModel,
        observation: SourceObservationModel,
        segment: BusinessIndexSegmentModel,
    ) -> list[ValidationResult]:
        payload = observation.raw_payload or {}
        item = SimpleNamespace(
            id=None,
            source_observation_id=observation.id,
            external_id=observation.external_id,
            source_url=observation.source_url,
            title=payload.get("title") or payload.get("displayName") or business.display_name,
            raw_payload=payload,
        )
        return self.evaluate(
            business=business,
            source_item=item,
            segment=segment,
        )

    def _identity(self, business, item, observed_at, expires_at) -> ValidationResult:
        supported = bool(business.phone or business.domain or item.external_id or item.source_url)
        return _result(
            business,
            item,
            None,
            "identity",
            "passed" if supported else "uncertain",
            100 if item.external_id else 90 if supported else 30,
            "Canonical identity has a stable provider or contact identifier."
            if supported
            else "Identity lacks a provider, domain, phone, or source URL identifier.",
            observed_at,
            expires_at,
        )

    def _business_type(self, business, item, observed_at, expires_at) -> ValidationResult:
        host = urlparse(item.source_url or "").netloc.lower().removeprefix("www.")
        title = _normalized(item.title or business.display_name)
        blocked = any(host == value or host.endswith(f".{value}") for value in BLOCKED_HOSTS)
        generic = _is_generic_business_title(title)
        directory = business.is_directory is True
        passed = not (blocked or generic or directory)
        reason = (
            "Candidate is a business record rather than an ad, directory, or generic service title."
            if passed
            else "Candidate is a marketplace, directory, or generic service listing."
        )
        return _result(
            business,
            item,
            None,
            "business_identity",
            "passed" if passed else "failed",
            90 if passed else 95,
            reason,
            observed_at,
            expires_at,
            evidence=[{"host": host, "title": title}],
        )

    def _trade(self, business, item, segment, observed_at, expires_at) -> ValidationResult:
        slug = segment.niche.slug if segment.niche else ""
        terms = _trade_terms(segment.niche)
        payload = item.raw_payload or {}
        provider_payload = payload.get("raw") if isinstance(payload.get("raw"), dict) else payload
        independent_fields = {
            "title": item.title,
            "snippet": payload.get("snippet"),
            "description": payload.get("description"),
            "primary_category": payload.get("category"),
            "primary_type": provider_payload.get("primaryTypeDisplayName"),
            "types": provider_payload.get("types"),
            "categories": provider_payload.get("categories"),
        }
        text = _normalized(json.dumps(independent_fields, default=str))
        matched = sorted(term for term in terms if term in text)
        spec = NICHE_BY_SLUG.get(slug)
        excluded = sorted(
            term for term in (spec.excluded_terms if spec else ()) if term in text
        )
        decisive_text = _normalized(
            " ".join(
                str(value or "")
                for value in (
                    independent_fields["title"],
                    independent_fields["primary_category"],
                    independent_fields["primary_type"],
                )
            )
        )
        decisive_exclusions = sorted(
            term
            for term in (spec.excluded_terms if spec else ())
            if term in decisive_text
        )
        status = (
            "failed"
            if decisive_exclusions
            else "passed"
            if matched
            else "uncertain"
        )
        return _result(
            business,
            item,
            segment,
            "trade",
            status,
            95 if decisive_exclusions else 95 if matched else 35,
            "Independent source fields conflict with the requested trade."
            if decisive_exclusions
            else "Independent source fields support the requested trade."
            if matched
            else "The discovery query is not independent evidence of the business trade.",
            observed_at,
            expires_at,
            evidence=[
                {
                    "matched_terms": matched,
                    "excluded_terms": excluded,
                    "decisive_excluded_terms": decisive_exclusions,
                    "niche": slug,
                }
            ],
        )

    def _location(self, business, item, segment, observed_at, expires_at) -> ValidationResult:
        center = market_center(segment.market_label)
        distance = None
        if center and business.latitude is not None and business.longitude is not None:
            distance = _distance_km(
                center[0], center[1], business.latitude, business.longitude
            )
        address = _normalized(" ".join([business.address or "", business.geography or ""]))
        location_matches, matched_market_terms = market_matches_location(
            segment.market_label,
            address,
        )
        supported = bool(
            (distance is not None and distance <= 75)
            or location_matches
        )
        return _result(
            business,
            item,
            segment,
            "location",
            "passed" if supported else "uncertain",
            95 if distance is not None and distance <= 75 else 85 if supported else 30,
            "Coordinates or address support the requested market."
            if supported
            else "Location could not be independently confirmed for the requested market.",
            observed_at,
            expires_at,
            evidence=[
                {
                    "distance_km": round(distance, 2) if distance is not None else None,
                    "matched_market_terms": matched_market_terms,
                }
            ],
        )


def _result(
    business,
    item,
    segment,
    validation_type,
    status,
    confidence,
    reason,
    observed_at,
    expires_at,
    *,
    evidence=None,
) -> ValidationResult:
    return ValidationResult(
        business_id=business.id,
        source_item_id=item.id,
        source_observation_id=getattr(item, "source_observation_id", None),
        niche_id=segment.niche_id if segment is not None else None,
        market_key=segment.market_key if segment is not None else None,
        validation_type=validation_type,
        status=status,
        confidence=confidence,
        reason=reason,
        evidence=evidence or [],
        validator="business_index_validator",
        validator_version=VALIDATOR_VERSION,
        observed_at=observed_at,
        expires_at=expires_at,
    )


def _normalized(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _is_generic_business_title(title: str) -> bool:
    return bool(
        title in GENERIC_TITLES
        or len(title) < 4
        or re.match(r"^find\s+.+\s+in\s+", title)
        or re.match(r"^top\s+\d+\s+", title)
        or re.search(r"\b(service|services|contractor|contractors)\s+near\s+me$", title)
        or re.search(r"\bfor\s+hire$", title)
    )


def _trade_terms(niche) -> set[str]:
    if niche is None:
        return set()
    descriptor = _normalized(
        " ".join([niche.slug or "", niche.label or "", niche.category or ""])
    )
    terms = set(TRADE_TERMS.get(niche.slug, set()))
    for aliases in TRADE_TERMS.values():
        if any(alias in descriptor for alias in aliases):
            terms.update(aliases)
    terms.update(
        token
        for token in descriptor.split()
        if len(token) >= 4 and token not in GENERIC_TRADE_TERMS
    )
    return terms


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))
