from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from niches.catalog import NICHE_BY_SLUG


GOOGLE_PLACES_PROVIDER_ID = "google_places"
AUTO_PROVIDER_ID = "auto"
OPENSTREETMAP_PROVIDER_ID = "openstreetmap"
CONFIGURED_SEARCH_PROVIDER_ID = "configured_search"
SEED_PROVIDER_ID = "seed"
RETIRED_SOURCE_PROVIDER_IDS = frozenset({"kijiji"})


def source_provider_is_retired(provider_id: str | None) -> bool:
    normalized = str(provider_id or "").strip().lower().replace("-", "_")
    leaf = normalized.replace(":", "/").rsplit("/", 1)[-1]
    return normalized in RETIRED_SOURCE_PROVIDER_IDS or leaf in RETIRED_SOURCE_PROVIDER_IDS


@dataclass(frozen=True)
class SourceProviderSpec:
    id: str
    label: str
    adapter_kind: str
    capabilities: frozenset[str]
    version: int = 1
    enabled: bool = True
    stage: int = 1
    priority: int = 100
    cost: str = "metered"
    detail: str = ""


@dataclass(frozen=True)
class SourceTemplateSpec:
    id: str
    provider_id: str
    niche_slug: str
    template: str
    version: int = 1
    enabled: bool = True
    purpose: str = "discovery"
    metadata: dict[str, Any] = field(default_factory=dict)


SOURCE_PROVIDERS: dict[str, SourceProviderSpec] = {
    GOOGLE_PLACES_PROVIDER_ID: SourceProviderSpec(
        id=GOOGLE_PLACES_PROVIDER_ID,
        label="Google Places",
        adapter_kind="google_places",
        capabilities=frozenset({"local_business", "phone", "ratings", "website_listing"}),
        stage=1,
        priority=10,
        detail="Structured local-business discovery.",
    ),
    OPENSTREETMAP_PROVIDER_ID: SourceProviderSpec(
        id=OPENSTREETMAP_PROVIDER_ID,
        label="OpenStreetMap",
        adapter_kind="openstreetmap",
        capabilities=frozenset({"local_business", "address", "phone", "website_listing"}),
        stage=2,
        priority=20,
        cost="free",
        detail="Public map-based local-business discovery.",
    ),
    CONFIGURED_SEARCH_PROVIDER_ID: SourceProviderSpec(
        id=CONFIGURED_SEARCH_PROVIDER_ID,
        label="Public web search",
        adapter_kind="configured_search",
        capabilities=frozenset({"public_web", "official_website", "directory_reference"}),
        stage=2,
        priority=25,
        detail="Public-web coverage and configured site recipes.",
    ),
    SEED_PROVIDER_ID: SourceProviderSpec(
        id=SEED_PROVIDER_ID,
        label="Seed import",
        adapter_kind="seed",
        capabilities=frozenset({"seed_import"}),
        stage=1,
        priority=5,
        cost="internal",
        detail="Curated or manually imported business records.",
    ),
}


_GOOGLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "home_service_painting": (
        "residential painters {location}",
        "house painters {location}",
        "painting contractors {location}",
        "interior painters {location}",
        "exterior painters {location}",
        "cabinet painters {location}",
    ),
    "home_service_hvac": (
        "HVAC contractors {location}",
        "heating and cooling companies {location}",
        "furnace and air conditioning service {location}",
    ),
    "home_service_roofing": (
        "roofing contractors {location}",
        "residential roofers {location}",
        "roof repair companies {location}",
    ),
    "home_service_plumbing": (
        "plumbers {location}",
        "plumbing contractors {location}",
        "residential plumbing services {location}",
    ),
    "home_service_electrical": (
        "electricians {location}",
        "electrical contractors {location}",
        "residential electrical services {location}",
    ),
    "home_service_cleaning": (
        "house cleaning companies {location}",
        "residential cleaning services {location}",
        "home cleaners {location}",
    ),
    "home_service_landscaping": (
        "landscaping companies {location}",
        "residential landscapers {location}",
        "lawn care services {location}",
    ),
    "home_service_pest_control": (
        "pest control companies {location}",
        "residential exterminators {location}",
        "wildlife and pest removal {location}",
    ),
    "home_service_garage_doors": (
        "garage door repair companies {location}",
        "garage door installers {location}",
        "overhead door service {location}",
    ),
}

_GOOGLE_PLACE_TYPES: dict[str, str] = {
    "home_service_painting": "painter",
    "home_service_roofing": "roofing_contractor",
    "home_service_plumbing": "plumber",
    "home_service_electrical": "electrician",
    "home_service_cleaning": "cleaning_service",
    "home_service_landscaping": "landscaper",
    "home_service_pest_control": "pest_control_service",
}

_OSM_TEMPLATES: dict[str, dict[str, Any]] = {
    "home_service_painting": {
        "query_label": "painting contractors",
        "name_pattern": "paint|painter|painting",
        "tag_filters": (("craft", "painter"),),
        "required_name_terms": ("paint", "painter", "painting"),
        "excluded_name_terms": ("art gallery", "auto body", "paint store", "supplies"),
    },
    "home_service_roofing": {
        "query_label": "roofing contractors",
        "name_pattern": "roofing|roofer",
        "tag_filters": (("craft", "roofer"),),
        "required_name_terms": ("roofing", "roofer"),
        "excluded_name_terms": ("supply", "supplies", "truss", "waterproof"),
    },
    "home_service_hvac": {
        "query_label": "HVAC heating and cooling contractors",
        "name_pattern": "hvac|heating|cooling|air conditioning",
        "tag_filters": (("craft", "hvac"),),
        "required_name_terms": ("hvac", "heating", "cooling", "air conditioning"),
        "excluded_name_terms": (
            "association",
            "hospital",
            "plant",
            "supply",
            "supplies",
            "water cooling system",
        ),
        "excluded_tag_terms": ("doityourself",),
    },
    "home_service_plumbing": {
        "query_label": "plumbing contractors",
        "name_pattern": "plumb|drain service",
        "tag_filters": (("craft", "plumber"),),
        "required_name_terms": ("plumb", "drain service"),
        "excluded_name_terms": ("supply", "supplies", "wholesale"),
    },
    "home_service_electrical": {
        "query_label": "electrical contractors",
        "name_pattern": "electric|electrical",
        "tag_filters": (("craft", "electrician"),),
        "required_name_terms": ("electric", "electrical"),
        "excluded_name_terms": ("supply", "supplies", "utility", "wholesale"),
    },
    "home_service_landscaping": {
        "query_label": "landscaping and lawn care companies",
        "name_pattern": "landscap|lawn care|garden service",
        "tag_filters": (("craft", "gardener"),),
        "required_name_terms": ("landscap", "lawn care", "garden service"),
        "excluded_name_terms": (
            "architect",
            "network",
            "pest",
            "station",
            "supply",
            "supplies",
        ),
    },
    "home_service_cleaning": {
        "query_label": "residential and house cleaning companies",
        "name_pattern": "cleaning|cleaners|maid",
        "tag_filters": (("craft", "cleaner"),),
        "required_name_terms": (
            "house cleaning",
            "home cleaning",
            "maid",
            "residential cleaning",
            "cleaning service",
        ),
        "excluded_name_terms": ("dry clean", "laundry", "carpet", "duct"),
        "excluded_tag_terms": ("dry_cleaning", "laundry", "clothes"),
    },
    "home_service_pest_control": {
        "query_label": "pest control and extermination services",
        "name_pattern": "pest control|exterminat|wildlife removal",
        "tag_filters": (("craft", "pest_control"),),
        "required_name_terms": ("pest control", "exterminat", "wildlife removal"),
        "excluded_name_terms": ("supply", "supplies", "product"),
    },
    "home_service_garage_doors": {
        "query_label": "garage door repair and installation services",
        "name_pattern": "garage door|overhead door",
        "tag_filters": (),
        "required_name_terms": ("garage door", "overhead door"),
        "excluded_name_terms": ("cabinet", "lumber", "supply", "supplies"),
    },
}


SOURCE_TEMPLATES: tuple[SourceTemplateSpec, ...] = tuple(
    SourceTemplateSpec(
        id=f"google_places:{niche_slug}:{index}",
        provider_id=GOOGLE_PLACES_PROVIDER_ID,
        niche_slug=niche_slug,
        template=template,
        purpose="discovery",
        metadata={"place_type": _GOOGLE_PLACE_TYPES.get(niche_slug)},
    )
    for niche_slug, templates in _GOOGLE_TEMPLATES.items()
    for index, template in enumerate(templates, start=1)
) + tuple(
    SourceTemplateSpec(
        id=f"openstreetmap:{niche_slug}:1",
        provider_id=OPENSTREETMAP_PROVIDER_ID,
        niche_slug=niche_slug,
        template=str(config["query_label"]),
        purpose="discovery",
        metadata={key: value for key, value in config.items() if key != "query_label"},
    )
    for niche_slug, config in _OSM_TEMPLATES.items()
)


def niche_slug_for_category(category: str) -> str | None:
    normalized = _normalize(category)
    if not normalized:
        return None
    normalized_slug = normalized.replace(" ", "_")
    if normalized_slug in NICHE_BY_SLUG:
        return normalized_slug
    best: tuple[int, str] | None = None
    for slug, spec in NICHE_BY_SLUG.items():
        descriptors = {
            _normalize(spec.category),
            _normalize(spec.niche_label),
            *(_normalize(term) for term in spec.trade_terms),
        }
        score = max(
            (
                len(descriptor)
                for descriptor in descriptors
                if descriptor and (descriptor in normalized or normalized in descriptor)
            ),
            default=0,
        )
        if score and (best is None or score > best[0]):
            best = (score, slug)
    return best[1] if best else None


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())
