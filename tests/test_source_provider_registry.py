from source_providers.catalog import SOURCE_PROVIDERS, niche_slug_for_category
from source_providers.registry import SourceProviderRegistry


def test_registry_centralizes_versioned_niche_templates() -> None:
    registry = SourceProviderRegistry()
    google_templates = registry.templates(provider_id="google_places")

    assert {template.niche_slug for template in google_templates} == {
        "home_service_painting",
        "home_service_hvac",
        "home_service_roofing",
        "home_service_plumbing",
        "home_service_electrical",
        "home_service_cleaning",
        "home_service_landscaping",
        "home_service_pest_control",
        "home_service_garage_doors",
    }
    assert all(template.version >= 1 for template in google_templates)
    assert all(template.enabled for template in google_templates)
    assert all(template.provider_id in SOURCE_PROVIDERS for template in google_templates)


def test_registry_resolves_profile_category_to_provider_templates() -> None:
    registry = SourceProviderRegistry()

    templates = registry.templates_for_category(
        "google_places", "garage-door repair and installation services"
    )

    assert niche_slug_for_category("garage-door services") == "home_service_garage_doors"
    assert [template.template for template in templates] == [
        "garage door repair companies {location}",
        "garage door installers {location}",
        "overhead door service {location}",
    ]


def test_configured_registry_controls_enabled_providers_and_custom_templates() -> None:
    registry = SourceProviderRegistry.configured(
        google_places_configured=False,
        search_configured=True,
        openstreetmap_enabled=True,
        apify_sources=[
            {
                "id": "local_directory",
                "label": "Local directory",
                "api_token": "token",
                "actor_id": "actor",
                "input_template": {"query": "{{query}}"},
                "version": 2,
            }
        ],
        source_templates=[
            {
                "id": "chamber-search",
                "provider_id": "configured_search",
                "niche_slug": "home_service_painting",
                "query_template": "site:example.ca {{query}}",
                "version": 3,
                "enabled": True,
            }
        ],
    )

    assert registry.provider("google_places").enabled is False
    assert registry.provider("openstreetmap").enabled is True
    assert registry.provider("local_directory").adapter_kind == "apify_actor"
    assert registry.provider("local_directory").version == 2
    assert registry.templates(
        provider_id="configured_search",
        niche_slug="home_service_painting",
    )[0].version == 3


def test_unconfigured_dynamic_provider_is_disabled() -> None:
    registry = SourceProviderRegistry.configured(
        google_places_configured=False,
        search_configured=False,
        openstreetmap_enabled=False,
        apify_sources=[{"id": "missing_actor", "enabled": True}],
    )

    assert registry.provider("missing_actor").enabled is False


def test_unknown_category_only_receives_provider_wide_templates() -> None:
    registry = SourceProviderRegistry(
        template_configs=[
            {
                "id": "global-search",
                "provider_id": "configured_search",
                "query_template": "{{query}} directory",
            },
            {
                "id": "painting-only",
                "provider_id": "configured_search",
                "niche_slug": "home_service_painting",
                "query_template": "{{query}} painters",
            },
        ]
    )

    templates = registry.templates_for_category(
        "configured_search", "unmapped specialist businesses"
    )

    assert [template.id for template in templates] == ["global-search"]
