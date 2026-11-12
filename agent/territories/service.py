from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from canonical.semantics import semantic_key
from business_index.schemas import OpportunityType, SearchContract
from db.models import (
    AudienceResultModel,
    AudienceRunModel,
    LeadOutcomeModel,
    NicheModel,
    SignalDefinitionModel,
    WorkspaceNichePreferenceModel,
)
from outcomes.policy import CONTACT_ATTEMPT_OUTCOMES, POSITIVE_OUTCOMES
from outcomes.schemas import LeadOutcome
from niches.resolver import resolve_niche
from products.repository import DEFAULT_WORKSPACE_ID, ProductRepository
from service_definitions.repository import ServiceDefinitionRepository
from shared.errors import NotFoundError, ValidationError
from shared.utils import new_id, normalize_text, utcnow
from territories.geocoding import GeocodedMarket, MarketGeocoder
from territories.repository import TerritoryRepository
from territories.schemas import (
    ProfileCreate,
    TerritoryCreate,
    TerritoryResolveRequest,
    TerritoryResolutionRead,
    TerritoryRead,
    TerritoryUpdate,
)


class TerritoryService:
    def __init__(
        self,
        session: Session,
        *,
        workspace_id: str | None,
        market_geocoder: MarketGeocoder | None = None,
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id or DEFAULT_WORKSPACE_ID
        self.products = ProductRepository(session, workspace_id=self.workspace_id)
        self.territories = TerritoryRepository(session, workspace_id=self.workspace_id)
        self.services = ServiceDefinitionRepository(session)
        self.market_geocoder = market_geocoder or MarketGeocoder(
            openstreetmap_enabled=False
        )

    def resolve(self, request: TerritoryResolveRequest) -> TerritoryResolutionRead:
        product = self.products.get(request.product_id)
        category, market_label = parse_territory_request(
            request.request,
            default_market=product.target_geography,
        )
        market_key = semantic_key(market_label) or "unknown"
        source_inputs = {
            "query": request.request,
            "source_request_intent": {
                "business_category": category,
                "location": market_label,
                "search_query": request.request,
            },
        }
        resolved = resolve_niche(
            self.session,
            source_inputs=source_inputs,
            source_input=request.request,
        )
        if resolved is not None:
            niche = self.session.get(NicheModel, resolved.niche_id)
            if niche is None:
                raise NotFoundError("resolved niche not found", {"niche_id": resolved.niche_id})
            return TerritoryResolutionRead(
                product_id=product.id,
                request=request.request,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                niche_category=niche.category or category,
                market_key=market_key,
                market_label=market_label,
                confidence=resolved.score,
                existing_niche=True,
            )

        label = _title_label(category)
        return TerritoryResolutionRead(
            product_id=product.id,
            request=request.request,
            niche_slug=_slug(category),
            niche_label=label,
            niche_category=category,
            market_key=market_key,
            market_label=market_label,
            confidence=0.5,
            existing_niche=False,
        )

    def create(
        self,
        data: TerritoryCreate,
        *,
        reuse_existing: bool = False,
        allow_duplicate: bool = False,
        commit: bool = True,
    ):
        if not data.confirmed:
            raise ValidationError("territory resolution must be confirmed before creation")
        if data.folder_id:
            from territories.folders import AudienceFolderService

            folder = AudienceFolderService(
                self.session,
                workspace_id=self.workspace_id,
            ).get(data.folder_id)
            if folder.product_id != data.product_id:
                raise ValidationError(
                    "audience folder belongs to another product",
                    {"folder_id": folder.id},
                )
        niche = self._confirmed_niche(data)
        is_profile = bool(data.service_keys or data.signal_keys)
        coordinates = (data.latitude, data.longitude)
        if is_profile and (coordinates[0] is None or coordinates[1] is None):
            resolved_market = self.market_geocoder.resolve(data.city or data.market_key)
            if resolved_market is None:
                raise ValidationError(
                    "market coordinates are unavailable",
                    {
                        "city": data.city or data.market_key,
                        "reason": "A radius audience requires a resolved center point.",
                    },
                )
            coordinates = (resolved_market.latitude, resolved_market.longitude)
        contract_payload = (
            {}
            if is_profile
            else data.search_contract
            or {
                "opportunity_type": OpportunityType.ANY.value,
                "search_contract": SearchContract().as_dict(),
            }
        )
        stored_contract_hash = str(contract_payload.get("contract_hash") or "").strip()
        if is_profile:
            criteria_hash = (
                data.criteria_hash
                if data.criteria_hash != "default"
                else _criteria_hash(_structured_profile_criteria(data))
            )
        else:
            criteria_hash = stored_contract_hash or (
                data.criteria_hash
                if data.criteria_hash != "default"
                else _criteria_hash(contract_payload)
            )
        normalized = data.model_copy(
            update={
                "niche_slug": niche.slug,
                "niche_label": niche.label,
                "market_key": semantic_key(data.market_key) or "unknown",
                "city": normalize_text(data.city or data.market_key),
                "place_label": normalize_text(data.place_label or data.city or data.market_key),
                "latitude": coordinates[0],
                "longitude": coordinates[1],
                "signal_keys": _clean_profile_keys(data.signal_keys),
                "service_keys": _clean_profile_keys(data.service_keys),
                "exclusion_keys": _clean_profile_keys(data.exclusion_keys),
                "search_contract": contract_payload,
                "criteria_hash": criteria_hash,
            }
        )
        return self.territories.create(
            normalized,
            niche_id=niche.id,
            reuse_existing=reuse_existing,
            allow_duplicate=allow_duplicate,
            commit=commit,
        )

    def create_profile(self, data: ProfileCreate, *, commit: bool = True):
        niche = self.session.get(NicheModel, data.niche_id)
        if niche is None or not niche.active:
            raise ValidationError(
                "selected business type is not available",
                {"niche_id": data.niche_id},
            )
        if data.clone_from_id:
            source_profile = self.territories.get(data.clone_from_id)
            if source_profile.product_id != data.product_id:
                raise ValidationError(
                    "cloned audience must belong to the same product",
                    {"audience_id": data.clone_from_id},
                )
        folder_id = data.folder_id
        if folder_id is None:
            from territories.folders import AudienceFolderService

            folder_id = AudienceFolderService(
                self.session,
                workspace_id=self.workspace_id,
            ).get_or_create_for_niche(product_id=data.product_id, niche=niche).id
        selected_markets = data.selected_markets()
        primary_market = selected_markets[0]
        place_label = normalize_text(primary_market.place_label)
        city = place_label.split(",", 1)[0].strip() or place_label
        customer_kind = data.customer_kind.value
        resolved_market = (
            GeocodedMarket(
                latitude=primary_market.latitude,
                longitude=primary_market.longitude,
                label=place_label,
                provider=primary_market.place_provider,
                external_id=primary_market.place_external_id,
                country_code=primary_market.country_code,
            )
            if data.markets
            else self.market_geocoder.resolve(place_label)
        )
        if resolved_market is None:
            raise ValidationError(
                "market coordinates are unavailable",
                {
                    "place": place_label,
                    "reason": "A profile radius requires a stored market center.",
                },
            )
        country_code = (resolved_market.country_code or primary_market.country_code or "").lower() or None
        if country_code and country_code not in {"ca", "us", "mx"}:
            raise ValidationError(
                "selected place is outside the supported market",
                {"country_code": country_code, "supported": ["ca", "us", "mx"]},
            )
        service_keys = list(dict.fromkeys(data.services))
        active_service_keys = {
            service.key for service in self.services.list(status="active")
        }
        unknown_services = sorted(set(service_keys) - active_service_keys)
        if unknown_services:
            raise ValidationError(
                "profile contains inactive or unknown services",
                {"service_keys": unknown_services},
            )
        mapped_signals = self.services.signal_keys(service_keys)
        signals = list(dict.fromkeys([*mapped_signals, *data.signals]))
        allowed_signals = {option["key"] for option in self.profile_signal_options()}
        unknown_signals = sorted(set(signals) - allowed_signals)
        if unknown_signals:
            raise ValidationError(
                "profile contains inactive or unknown signals",
                {"signal_keys": unknown_signals},
            )
        exclusions = [exclusion.value for exclusion in data.exclude]
        locations = []
        if data.markets:
            seen_location_ids: set[str] = set()
            for market in selected_markets:
                location_id = market.place_external_id or semantic_key(market.place_label)
                if not location_id or location_id in seen_location_ids:
                    continue
                seen_location_ids.add(location_id)
                location_city = normalize_text(
                    market.city or market.place_label.split(",", 1)[0]
                )
                locations.append(
                    {
                        "id": location_id,
                        "city": location_city,
                        "label": normalize_text(market.place_label),
                        "provider": market.place_provider,
                        "external_id": market.place_external_id,
                        "country_code": (market.country_code or "").lower() or None,
                        "region_code": market.region_code,
                        "region_name": market.region_name,
                        "latitude": market.latitude,
                        "longitude": market.longitude,
                    }
                )
        criteria = {
            "niche_id": niche.id,
            "customer_kind": customer_kind,
            "min_google_rating": data.min_google_rating,
            "min_review_count": data.min_review_count,
            "max_review_count": data.max_review_count,
            "city": semantic_key(city),
            "radius_km": primary_market.radius_km,
            "locations": [location["id"] for location in locations],
            "signals": signals,
            "services": service_keys,
            "exclude": exclusions,
            "limit": data.limit,
            "exclude_already_delivered": True,
        }
        profile = self.create(
            TerritoryCreate(
                product_id=data.product_id,
                folder_id=folder_id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                niche_category=niche.category,
                market_key=place_label,
                city=city,
                place_label=resolved_market.label,
                place_provider=resolved_market.provider,
                place_external_id=resolved_market.external_id,
                country_code=country_code,
                latitude=resolved_market.latitude,
                longitude=resolved_market.longitude,
                radius_km=primary_market.radius_km,
                locations=locations,
                customer_kind=data.customer_kind,
                min_google_rating=data.min_google_rating,
                min_review_count=data.min_review_count,
                max_review_count=data.max_review_count,
                service_keys=service_keys,
                signal_keys=signals,
                exclusion_keys=exclusions,
                label=data.name or (
                    (
                        f"{niche.label} in {len(locations)} cities"
                        if len(locations) > 1
                        else f"{niche.label} in {city}"
                    )
                    if data.markets
                    else f"{niche.label} near {city}"
                ),
                refill_policy=data.refill_policy,
                batch_size=data.limit,
                criteria_hash=_criteria_hash(criteria),
                confirmed=True,
            ),
            reuse_existing=True,
            allow_duplicate=bool(data.clone_from_id),
            commit=commit,
        )
        interval_days = {
            "weekly": 7,
            "biweekly": 14,
            "monthly": 30,
        }.get(data.refill_policy.value)
        profile.next_run_at = (
            utcnow() + timedelta(days=interval_days)
            if interval_days is not None
            else None
        )
        profile.folder_id = folder_id
        if commit:
            self.session.commit()
            self.session.refresh(profile)
        else:
            self.session.flush()
        return profile

    def profile_options(self) -> list[dict[str, str]]:
        rows = self._trade_rows(include_hidden=False)
        return [
            {
                "id": niche.id,
                "key": niche.slug,
                "label": niche.label,
                "category": niche.category,
            }
            for niche, _preference in rows
        ]

    def trade_catalog(self) -> list[dict[str, object]]:
        return [
            _trade_catalog_item(niche, preference)
            for niche, preference in self._trade_rows(include_hidden=True)
        ]

    def create_trade(self, label: str) -> dict[str, object]:
        cleaned = normalize_text(label)
        if len(cleaned) < 2:
            raise ValidationError("trade name is required")
        duplicate = self.session.scalar(
            select(NicheModel).where(
                func.lower(NicheModel.label) == cleaned.lower(),
                NicheModel.active.is_(True),
                or_(
                    NicheModel.created_by_workspace_id.is_(None),
                    NicheModel.created_by_workspace_id == self.workspace_id,
                ),
            )
        )
        if duplicate is not None:
            preference = self._trade_preference(
                duplicate.id,
                display_order=duplicate.display_order,
            )
            preference.enabled = True
            self.session.commit()
            return _trade_catalog_item(duplicate, preference)
        base_slug = _slug(cleaned)
        slug = base_slug
        suffix = 2
        while self.session.scalar(select(NicheModel.id).where(NicheModel.slug == slug)):
            slug = f"{base_slug}_{suffix}"
            suffix += 1
        max_order = max(
            (item[0].display_order for item in self._trade_rows(include_hidden=True)),
            default=0,
        )
        terms = _default_trade_terms(cleaned)
        niche = NicheModel(
            id=new_id("niche"),
            slug=slug,
            label=cleaned,
            category=cleaned,
            default_query=cleaned,
            active=True,
            catalog_status="custom",
            display_order=int(max_order) + 1,
            created_by_workspace_id=self.workspace_id,
            search_config={"include_terms": list(dict.fromkeys(terms)), "exclude_terms": []},
        )
        self.session.add(niche)
        self.session.flush()
        preference = self._trade_preference(
            niche.id,
            display_order=niche.display_order,
        )
        preference.enabled = True
        preference.display_order = niche.display_order
        self.session.commit()
        self.session.refresh(niche)
        return _trade_catalog_item(niche, preference)

    def update_trade(
        self,
        niche_id: str,
        *,
        active: bool,
    ) -> dict[str, object]:
        niche = self.session.get(NicheModel, niche_id)
        if niche is None or niche.created_by_workspace_id not in {None, self.workspace_id}:
            raise NotFoundError("trade not found", {"trade_id": niche_id})
        preference = self._trade_preference(
            niche.id,
            display_order=niche.display_order,
        )
        preference.enabled = active
        self.session.commit()
        return _trade_catalog_item(niche, preference)

    def _trade_rows(
        self,
        *,
        include_hidden: bool,
    ) -> list[tuple[NicheModel, WorkspaceNichePreferenceModel | None]]:
        statement = (
            select(NicheModel, WorkspaceNichePreferenceModel)
            .outerjoin(
                WorkspaceNichePreferenceModel,
                and_(
                    WorkspaceNichePreferenceModel.niche_id == NicheModel.id,
                    WorkspaceNichePreferenceModel.workspace_id == self.workspace_id,
                ),
            )
            .where(
                NicheModel.active.is_(True),
                NicheModel.catalog_status.in_(("supported", "custom")),
                or_(
                    NicheModel.created_by_workspace_id.is_(None),
                    NicheModel.created_by_workspace_id == self.workspace_id,
                ),
            )
            .order_by(
                func.coalesce(
                    WorkspaceNichePreferenceModel.display_order,
                    NicheModel.display_order,
                ),
                NicheModel.label,
            )
        )
        if not include_hidden:
            statement = statement.where(
                or_(
                    WorkspaceNichePreferenceModel.enabled.is_(None),
                    WorkspaceNichePreferenceModel.enabled.is_(True),
                )
            )
        return list(self.session.execute(statement).tuples())

    def _trade_preference(
        self,
        niche_id: str,
        *,
        display_order: int,
    ) -> WorkspaceNichePreferenceModel:
        preference = self.session.get(
            WorkspaceNichePreferenceModel,
            (self.workspace_id, niche_id),
        )
        if preference is None:
            preference = WorkspaceNichePreferenceModel(
                workspace_id=self.workspace_id,
                niche_id=niche_id,
                enabled=True,
                display_order=display_order,
            )
            self.session.add(preference)
        return preference

    def profile_signal_options(self) -> list[dict[str, str]]:
        definitions = list(
            self.session.scalars(
                select(SignalDefinitionModel)
                .where(
                    SignalDefinitionModel.status == "active",
                    SignalDefinitionModel.opportunity_direction != "none",
                )
                .order_by(SignalDefinitionModel.category, SignalDefinitionModel.label)
            )
        )
        if definitions:
            return [
                {
                    "key": definition.key,
                    "label": definition.label,
                    "category": definition.category,
                }
                for definition in definitions
            ]
        labels = {
            "website_unavailable": "Missing or unavailable website",
            "no_quote_flow": "No quote or booking flow",
            "no_contact_form": "No contact form",
            "reviews_under_15": "Reviews under 15",
        }
        return [
            {"key": key, "label": label, "category": "legacy"}
            for key, label in labels.items()
        ]

    def profile_service_options(self) -> list[dict]:
        options = []
        for service in self.services.list():
            # Inactive services are retired catalog entries. Draft services are
            # still returned as honest "upcoming" options, while retired broad
            # groupings must not leak back into audience creation.
            if service.status == "inactive":
                continue
            signals = [
                {
                    "key": mapping.signal_definition.key,
                    "label": mapping.signal_definition.label,
                    "weight": mapping.weight,
                }
                for mapping in sorted(
                    service.signal_mappings,
                    key=lambda item: item.sort_order,
                )
                if mapping.signal_definition.status == "active"
                and mapping.signal_definition.opportunity_direction != "none"
            ]
            options.append({
                "key": service.key,
                "label": service.label,
                "description": service.description,
                "status": service.status,
                "enabled": service.status == "active" and bool(signals),
                "signals": signals,
            })
        return options

    def list(self):
        return [self._read(model) for model in self.territories.list()]

    def get(self, territory_id: str):
        return self.territories.get(territory_id)

    def get_read(self, territory_id: str) -> TerritoryRead:
        return self._read(self.territories.get(territory_id))

    def update(self, territory_id: str, update: TerritoryUpdate):
        model = self.territories.get(territory_id)
        values = update.model_dump(mode="python", exclude_unset=True)
        if "locations" in values:
            locations = values["locations"] or []
            normalized_locations: list[dict] = []
            seen_location_ids: set[str] = set()
            for location in locations:
                location_id = normalize_text(str(location.get("id") or location.get("external_id") or ""))
                city = normalize_text(str(location.get("city") or ""))
                label = normalize_text(str(location.get("label") or city))
                latitude = location.get("latitude")
                longitude = location.get("longitude")
                if not location_id or not city or latitude is None or longitude is None:
                    raise ValidationError(
                        "each selected city requires an id, name, and coordinates",
                        {"location": location},
                    )
                if location_id in seen_location_ids:
                    continue
                seen_location_ids.add(location_id)
                normalized_locations.append({
                    "id": location_id,
                    "city": city,
                    "label": label,
                    "provider": location.get("provider") or "geonames",
                    "external_id": location.get("external_id") or location_id,
                    "country_code": (str(location.get("country_code") or "").lower() or None),
                    "region_code": location.get("region_code"),
                    "region_name": location.get("region_name"),
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                })
            if not normalized_locations:
                raise ValidationError("select at least one city")
            values["locations"] = normalized_locations
            primary = normalized_locations[0]
            values.update({
                "city": primary["city"],
                "place_label": primary["label"],
                "place_provider": primary["provider"],
                "place_external_id": primary["external_id"],
                "country_code": primary["country_code"],
                "latitude": primary["latitude"],
                "longitude": primary["longitude"],
                "market_key": semantic_key(primary["label"]) or model.market_key,
            })
        if "niche_id" in values:
            niche = self.session.get(NicheModel, values["niche_id"])
            if niche is None or not niche.active:
                raise ValidationError(
                    "selected business type is not available",
                    {"niche_id": values["niche_id"]},
                )
        if "folder_id" in values and values["folder_id"] is not None:
            from territories.folders import AudienceFolderService

            folder = AudienceFolderService(
                self.session,
                workspace_id=self.workspace_id,
            ).get(values["folder_id"])
            if folder.product_id != model.product_id:
                raise ValidationError(
                    "audience folder belongs to another product",
                    {"folder_id": folder.id},
                )
        if "locations" not in values and ("place_label" in values or "city" in values):
            requested_place = normalize_text(
                values.get("place_label") or values.get("city") or model.place_label or model.city
            )
            resolved_market = self.market_geocoder.resolve(requested_place)
            if resolved_market is None:
                raise ValidationError(
                    "market coordinates are unavailable",
                    {
                        "place": requested_place,
                        "reason": "A profile radius requires a stored market center.",
                    },
                )
            country_code = (resolved_market.country_code or values.get("country_code") or "").lower() or None
            if country_code and country_code not in {"ca", "us", "mx"}:
                raise ValidationError(
                    "selected place is outside the supported market",
                    {"country_code": country_code, "supported": ["ca", "us", "mx"]},
                )
            values.update({
                "city": requested_place.split(",", 1)[0].strip() or requested_place,
                "place_label": resolved_market.label,
                "place_provider": resolved_market.provider,
                "place_external_id": resolved_market.external_id,
                "country_code": country_code,
                "latitude": resolved_market.latitude,
                "longitude": resolved_market.longitude,
                "market_key": semantic_key(resolved_market.label) or model.market_key,
            })
        if "signal_keys" in values:
            values["signal_keys"] = _clean_profile_keys(values["signal_keys"])
        if "exclusion_keys" in values:
            values["exclusion_keys"] = _clean_profile_keys(values["exclusion_keys"])
        if "customer_kind" in values and hasattr(values["customer_kind"], "value"):
            values["customer_kind"] = values["customer_kind"].value
        if "service_keys" in values:
            service_keys = _clean_profile_keys(values["service_keys"])
            active_service_keys = {
                service.key for service in self.services.list(status="active")
            }
            unknown_services = sorted(set(service_keys) - active_service_keys)
            if unknown_services:
                raise ValidationError(
                    "Unknown or inactive services",
                    {"service_keys": unknown_services},
                )
            values["service_keys"] = service_keys
            values["signal_keys"] = self.services.signal_keys(service_keys)
        prospective_latitude = values.get("latitude", model.latitude)
        prospective_longitude = values.get("longitude", model.longitude)
        location_changed = bool({"city", "place_label", "radius_km", "locations"} & values.keys())
        if location_changed and (prospective_latitude is None or prospective_longitude is None):
            raise ValidationError(
                "market coordinates are unavailable",
                {
                    "city": values.get("city", model.city),
                    "reason": "A radius audience requires a resolved center point.",
                },
            )
        criteria_fields = {
            "niche_id",
            "city",
            "place_label",
            "radius_km",
            "locations",
            "customer_kind",
            "min_google_rating",
            "min_review_count",
            "max_review_count",
            "service_keys",
            "signal_keys",
            "exclusion_keys",
            "batch_size",
            "min_fit",
        }
        criteria_changed = bool(criteria_fields & values.keys())
        prospective_min_reviews = values.get("min_review_count", model.min_review_count)
        prospective_max_reviews = values.get("max_review_count", model.max_review_count)
        if (
            prospective_min_reviews is not None
            and prospective_max_reviews is not None
            and prospective_min_reviews > prospective_max_reviews
        ):
            raise ValidationError(
                "minimum review count cannot exceed maximum review count",
                {
                    "min_review_count": prospective_min_reviews,
                    "max_review_count": prospective_max_reviews,
                },
            )
        normalized = TerritoryUpdate.model_validate(
            {key: value for key, value in values.items() if key != "market_key"}
        )
        model = self.territories.update(territory_id, normalized, commit=False)
        if "market_key" in values:
            model.market_key = values["market_key"]
        if criteria_changed:
            model.criteria_version += 1
            criteria = {
                "niche_id": model.niche_id,
                "city": model.city,
                "radius_km": model.radius_km,
                "locations": [location.get("id") for location in (model.locations or [])],
                "customer_kind": model.customer_kind,
                "min_google_rating": model.min_google_rating,
                "min_review_count": model.min_review_count,
                "max_review_count": model.max_review_count,
                "service_keys": model.service_keys,
                "signal_keys": model.signal_keys,
                "exclusion_keys": model.exclusion_keys,
                "batch_size": model.batch_size,
                "min_fit": model.min_fit,
            }
            model.criteria_hash = _criteria_hash(criteria)
        if "refill_policy" in values:
            policy = (
                values["refill_policy"].value
                if hasattr(values["refill_policy"], "value")
                else str(values["refill_policy"])
            )
            interval_days = {"weekly": 7, "biweekly": 14, "monthly": 30}.get(policy)
            model.next_run_at = (
                utcnow() + timedelta(days=interval_days)
                if interval_days is not None
                else None
            )
        self.session.commit()
        self.session.refresh(model)
        return model

    def delete(self, territory_id: str) -> None:
        self.territories.delete(territory_id)

    def _read(self, model) -> TerritoryRead:
        latest_run = self.session.scalar(
            select(AudienceRunModel)
            .where(
                AudienceRunModel.audience_id == model.id,
                AudienceRunModel.state.in_(("ready", "partial")),
            )
            .order_by(AudienceRunModel.created_at.desc())
            .limit(1)
        )
        batch_results = (
            list(
                self.session.scalars(
                    select(AudienceResultModel).where(
                        AudienceResultModel.run_id == latest_run.id
                    )
                )
            )
            if latest_run is not None
            else []
        )
        outcomes = list(
            self.session.scalars(
                select(LeadOutcomeModel).where(
                    LeadOutcomeModel.workspace_id == self.workspace_id,
                    LeadOutcomeModel.territory_id == model.id,
                )
            )
        )
        contacted = {
            outcome.lead_id
            for outcome in outcomes
            if LeadOutcome(outcome.outcome) in CONTACT_ATTEMPT_OUTCOMES
        }
        positive = {
            outcome.lead_id
            for outcome in outcomes
            if LeadOutcome(outcome.outcome) in POSITIVE_OUTCOMES
        }
        return TerritoryRead.model_validate(model).model_copy(
            update={
                "niche_label": model.niche.label if model.niche else None,
                "last_batch_count": len(batch_results),
                "unreviewed_batch_count": sum(
                    result.review_status == "unreviewed"
                    for result in batch_results
                ),
                "positive_outcome_rate": (
                    round(len(contacted & positive) / len(contacted), 4)
                    if contacted
                    else 0.0
                ),
            }
        )

    def _confirmed_niche(self, data: TerritoryCreate) -> NicheModel:
        if data.niche_id:
            niche = self.session.scalar(
                select(NicheModel).where(
                    NicheModel.id == data.niche_id,
                    NicheModel.active.is_(True),
                )
            )
            if niche is None:
                raise NotFoundError("niche not found", {"niche_id": data.niche_id})
            return niche
        existing = self.session.scalar(
            select(NicheModel).where(NicheModel.slug == _slug(data.niche_slug)).limit(1)
        )
        if existing is not None:
            return existing
        niche = NicheModel(
            id=new_id("niche"),
            slug=_slug(data.niche_slug),
            label=normalize_text(data.niche_label),
            category=normalize_text(data.niche_category or data.niche_label),
            default_query=f"{data.niche_label} in {data.market_key}",
            active=True,
        )
        self.session.add(niche)
        self.session.flush()
        return niche


def parse_territory_request(value: str, *, default_market: str) -> tuple[str, str]:
    normalized = normalize_text(value)
    match = re.match(r"^(?P<category>.+?)\s+in\s+(?P<market>.+)$", normalized, flags=re.I)
    if match:
        category = normalize_text(match.group("category"))
        market = normalize_text(match.group("market"))
        if category and market:
            return category, market
    return normalized, normalize_text(default_market) or "unknown"


def _slug(value: str) -> str:
    slug = (semantic_key(value) or "local_business").replace(" ", "_")
    return slug[:255]


def _trade_catalog_item(
    niche: NicheModel,
    preference: WorkspaceNichePreferenceModel | None,
) -> dict[str, object]:
    return {
        "id": niche.id,
        "key": niche.slug,
        "label": niche.label,
        "category": niche.category,
        "active": preference.enabled if preference is not None else True,
        "display_order": (
            preference.display_order if preference is not None else niche.display_order
        ),
    }


def _default_trade_terms(label: str) -> list[str]:
    normalized = semantic_key(label) or label.lower()
    terms = [normalized]
    if normalized.endswith("s") and len(normalized) > 3:
        terms.append(normalized[:-1])
    return list(dict.fromkeys(terms))


def _title_label(value: str) -> str:
    return " ".join(
        word.upper() if word.lower() in {"hvac", "b2b"} else word.title()
        for word in value.split()
    )


def _criteria_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _structured_profile_criteria(data: TerritoryCreate) -> dict:
    return {
        "niche_id": data.niche_id,
        "customer_kind": data.customer_kind.value,
        "min_google_rating": data.min_google_rating,
        "min_review_count": data.min_review_count,
        "max_review_count": data.max_review_count,
        "city": semantic_key(data.city or data.market_key),
        "radius_km": data.radius_km,
        "locations": [location.get("id") for location in data.locations],
        "services": list(data.service_keys),
        "signals": list(data.signal_keys),
        "exclude": list(data.exclusion_keys),
        "limit": data.batch_size,
        "exclude_already_delivered": True,
    }


def _clean_keys(values: list[str]) -> list[str]:
    return list(dict.fromkeys(semantic_key(value) for value in values if semantic_key(value)))


def _clean_profile_keys(values: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            key.replace(" ", "_")
            for value in values
            if (key := semantic_key(value))
        )
    )
