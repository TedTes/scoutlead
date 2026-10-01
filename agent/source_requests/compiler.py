from __future__ import annotations

import re
from typing import Any

from evaluation.digital_opportunity import (
    product_requires_digital_opportunity,
    text_requires_digital_opportunity,
    website_opportunity_policy,
)
from products.discovery_policy import (
    build_local_business_queries,
    normalize_places_region_code,
)
from products.schemas import ProductRead
from shared.errors import ValidationError
from shared.utils import normalize_text, truncate
from source_requests.schemas import (
    AUTO_PROVIDER_ID,
    CONFIGURED_SEARCH_PROVIDER_ID,
    GOOGLE_PLACES_PROVIDER_ID,
    OPENSTREETMAP_PROVIDER_ID,
    SourceProviderKind,
    SourceRequestAction,
    SourceRequestCreate,
    SourceRequestIntent,
    SourceRequestPlan,
    SourceTask,
)


URL_INPUT_KINDS = {
    SourceProviderKind.URL_LIST.value,
    SourceProviderKind.SEARCH_URL.value,
    SourceProviderKind.CLASSIFIED_SEARCH_URL.value,
}
DEFAULT_SOURCE_RESULT_QUOTA = 25

_REQUEST_PREFIX_RE = re.compile(
    r"^(?:please\s+)?(?:find|list|show|search\s+for|look\s+for)\s+",
    flags=re.IGNORECASE,
)
_CONTACT_SUFFIX_RE = re.compile(
    r"\s+(?:business|businesses|company|companies|contacts?|leads?)\s*$",
    flags=re.IGNORECASE,
)
_REQUEST_QUALIFIER_RE = re.compile(
    r"\s+(?:with|without|that\s+have|that\s+do\s+not\s+have)\s+.+$",
    flags=re.IGNORECASE,
)


class SourceRequestCompiler:
    def compile_google_places(
        self,
        *,
        request: SourceRequestCreate,
        product: ProductRead,
        intent: SourceRequestIntent | None = None,
    ) -> SourceRequestPlan:
        intent = intent or self._interpret(
            request=request, product=product, source=GOOGLE_PLACES_PROVIDER_ID
        )
        requires_digital_opportunity = (
            product_requires_digital_opportunity(product)
            or text_requires_digital_opportunity(request.prompt)
        )
        website_policy = website_opportunity_policy(product, request.prompt)
        queries = build_local_business_queries(
            business_category=intent.business_category,
            location=intent.location,
            fallback_query=intent.search_query,
            expand_local_market=requires_digital_opportunity,
        )
        query = queries[0]
        region_code = normalize_places_region_code(intent.country or product.target_geography)
        return SourceRequestPlan(
            source=GOOGLE_PLACES_PROVIDER_ID,
            action=SourceRequestAction.LIST_CONTACTS,
            query=query,
            max_results=request.max_results,
            source_preset_id="google-places-local-business",
            explanation=(
                "List contacts by searching Google Places for local businesses. "
                "No outreach drafts are created for source requests."
            ),
            intent=intent,
            source_inputs={
                "compiled_query": query,
                "search_queries": queries,
                "website_policy": website_policy,
                "region_code": region_code,
                "compiled_provider_input": {
                    "textQuery": query,
                    "pageSize": request.max_results,
                    "regionCode": region_code,
                },
            },
            tasks=[
                SourceTask(
                    provider_id=GOOGLE_PLACES_PROVIDER_ID,
                    query=query,
                    stage=1,
                    priority=10,
                    max_results=min(request.max_results, DEFAULT_SOURCE_RESULT_QUOTA),
                    reason="Primary structured local-business discovery.",
                    input={
                        "search_queries": queries,
                        "business_category": intent.business_category,
                        "location": intent.location,
                        "website_policy": website_policy,
                    },
                    config={
                        "search_queries": queries,
                        "website_policy": website_policy,
                        "region_code": region_code,
                    },
                )
            ],
        )

    def compile_apify_source(
        self,
        *,
        request: SourceRequestCreate,
        product: ProductRead,
        source_config: dict[str, Any],
        intent: SourceRequestIntent | None = None,
    ) -> SourceRequestPlan:
        source_id = str(source_config.get("id") or request.source).strip()
        source_label = str(source_config.get("label") or source_id)
        intent = intent or self._interpret(request=request, product=product, source=source_id)
        quota_request = request.model_copy(
            update={"max_results": min(request.max_results, DEFAULT_SOURCE_RESULT_QUOTA)}
        )
        values = _template_values(
            request=quota_request,
            product=product,
            source_config=source_config,
            intent=intent,
        )
        actor_input = self._compile_actor_input(
            source_id=source_id,
            source_label=source_label,
            source_config=source_config,
            values=values,
        )
        query = normalize_text(values.get("source_url") or intent.search_query)
        return SourceRequestPlan(
            source=source_id,
            action=SourceRequestAction.LIST_CONTACTS,
            query=query,
            max_results=request.max_results,
            source_preset_id="apify-actor-source",
            explanation=(
                f"List contacts by searching {source_label}. "
                "No outreach drafts are created for source requests."
            ),
            intent=intent,
            source_inputs={
                "compiled_query": query,
                "compiled_provider_input": actor_input,
                "actor_input": actor_input,
                "result_mapping": source_config.get("result_mapping"),
                "input_kind": source_config.get("input_kind"),
            },
            tasks=[
                SourceTask(
                    provider_id=source_id,
                    query=query,
                    stage=3,
                    priority=30,
                    max_results=min(request.max_results, DEFAULT_SOURCE_RESULT_QUOTA),
                    reason=f"Configured fallback discovery through {source_label}.",
                    input={
                        "business_category": intent.business_category,
                        "location": intent.location,
                    },
                    config={
                        "actor_input": actor_input,
                        "result_mapping": source_config.get("result_mapping"),
                    },
                    budget_limit=source_config.get("max_charge_usd"),
                )
            ],
        )

    def compile_auto(
        self,
        *,
        request: SourceRequestCreate,
        product: ProductRead,
        google_places_configured: bool,
        search_configured: bool,
        openstreetmap_enabled: bool,
        apify_sources: list[dict[str, Any]],
        source_recipes: list[dict[str, Any]],
    ) -> SourceRequestPlan:
        intent = self._interpret(request=request, product=product, source=AUTO_PROVIDER_ID)
        google_plan = self.compile_google_places(
            request=request,
            product=product,
            intent=intent,
        )
        website_policy = str(google_plan.source_inputs.get("website_policy") or "any")
        queries = list(google_plan.source_inputs.get("search_queries") or [google_plan.query])
        tasks: list[SourceTask] = []
        if google_places_configured:
            tasks.extend(
                task.model_copy(update={"max_results": DEFAULT_SOURCE_RESULT_QUOTA})
                for task in google_plan.tasks
            )
        if openstreetmap_enabled:
            tasks.append(
                SourceTask(
                    provider_id=OPENSTREETMAP_PROVIDER_ID,
                    query=intent.search_query,
                    stage=2,
                    priority=20,
                    max_results=DEFAULT_SOURCE_RESULT_QUOTA,
                    reason="Expand local-business coverage with open map data.",
                    input={
                        "business_category": intent.business_category,
                        "location": intent.location,
                        "website_policy": website_policy,
                    },
                    config={"website_policy": website_policy},
                )
            )
        if search_configured:
            tasks.append(
                SourceTask(
                    provider_id=CONFIGURED_SEARCH_PROVIDER_ID,
                    query=intent.search_query,
                    stage=2,
                    priority=25,
                    max_results=DEFAULT_SOURCE_RESULT_QUOTA,
                    reason="Expand coverage through public-web business results.",
                    input={
                        "source_type": "web_search",
                        "business_category": intent.business_category,
                        "location": intent.location,
                    },
                    config={"website_policy": website_policy},
                )
            )
        if search_configured:
            for index, recipe in enumerate(source_recipes):
                query = _render_search_recipe(recipe, intent=intent, product=product)
                if not query:
                    continue
                tasks.append(
                    SourceTask(
                        provider_id=CONFIGURED_SEARCH_PROVIDER_ID,
                        query=query,
                        stage=int(recipe.get("stage") or 3),
                        priority=int(recipe.get("priority") or 40 + index),
                        max_results=min(
                            DEFAULT_SOURCE_RESULT_QUOTA,
                            int(recipe.get("max_results") or DEFAULT_SOURCE_RESULT_QUOTA),
                        ),
                        reason=str(
                            recipe.get("reason")
                            or f"Search configured public source {recipe['id']}."
                        ),
                        input={
                            "source_type": "web_search",
                            "source_recipe_id": recipe["id"],
                            "business_category": intent.business_category,
                            "location": intent.location,
                        },
                        config={"website_policy": website_policy},
                    )
                )
        for source_config in apify_sources:
            source_id = str(source_config.get("id") or "").strip()
            if not source_id:
                continue
            apify_plan = self.compile_apify_source(
                request=request.model_copy(update={"max_results": DEFAULT_SOURCE_RESULT_QUOTA}),
                product=product,
                source_config=source_config,
                intent=intent,
            )
            tasks.extend(
                task.model_copy(update={"max_results": DEFAULT_SOURCE_RESULT_QUOTA})
                for task in apify_plan.tasks
            )
        return SourceRequestPlan(
            source=AUTO_PROVIDER_ID,
            action=SourceRequestAction.LIST_CONTACTS,
            query=google_plan.query,
            max_results=request.max_results,
            source_preset_id="dynamic-discovery",
            explanation=(
                "Search the business index immediately, then use every configured live "
                "discovery source to expand coverage in the background."
            ),
            intent=intent,
            source_inputs={
                **google_plan.source_inputs,
                "search_queries": queries,
                "discovery_strategy": "staged",
                "discovery_tasks": [task.model_dump(mode="json") for task in tasks],
            },
            tasks=tasks,
        )

    def _interpret(
        self,
        *,
        request: SourceRequestCreate,
        product: ProductRead,
        source: str,
    ) -> SourceRequestIntent:
        category, location = _deterministic_request_scope(
            prompt=request.prompt,
            explicit_category=request.business_category,
            explicit_geography=request.geography,
            default_category=product.target_customer,
            default_geography=product.target_geography,
        )
        search_query = normalize_text(f"{category} in {location}")
        return SourceRequestIntent(
            business_category=category,
            location=location,
            country=_country_hint(location or product.target_geography),
            required_signals=_required_signals(request.prompt),
            excluded_result_types=["directories", "closed businesses", "national chains"],
            search_query=search_query,
            confidence=90 if request.business_category and request.geography else 75,
            rationale="Deterministically parsed from structured fields and the request text.",
        )

    @staticmethod
    def _compile_actor_input(
        *,
        source_id: str,
        source_label: str,
        source_config: dict[str, Any],
        values: dict[str, Any],
    ) -> dict[str, Any]:
        input_template = source_config.get("input_template")
        input_kind = str(source_config.get("input_kind") or "").strip()
        search_url_template = str(
            source_config.get("search_url_template")
            or source_config.get("url_template")
            or ""
        ).strip()

        if search_url_template and not values.get("source_url"):
            values["source_url"] = _render_template(search_url_template, values)

        if input_kind in URL_INPUT_KINDS and not values.get("source_url"):
            raise ValidationError(
                f"{source_label} needs a compiled source URL before it can run",
                {
                    "source": source_id,
                    "input_kind": input_kind,
                    "required_config": "Add search_url_template to the source config, or submit a source URL.",
                    "prompt": values.get("original_prompt"),
                },
            )

        if input_template:
            rendered = _render_template(input_template, values)
            if not isinstance(rendered, dict):
                raise ValidationError(
                    f"{source_label} input_template must render to an object",
                    {"source": source_id, "rendered_type": type(rendered).__name__},
                )
            return rendered

        if values.get("source_url"):
            return {
                "urls": [{"url": values["source_url"]}],
                "maxRecords": values["limit"],
            }

        raise ValidationError(
            f"{source_label} is missing an Apify input template",
            {
                "source": source_id,
                "required_config": (
                    "Add input_template to this APIFY_SOURCES entry so ScoutLead can "
                    "convert the interpreted request into the actor's expected payload."
                ),
                "available_values": sorted(values.keys()),
            },
        )


def _template_values(
    *,
    request: SourceRequestCreate,
    product: ProductRead,
    source_config: dict[str, Any],
    intent: SourceRequestIntent,
) -> dict[str, Any]:
    location = normalize_text(intent.location)
    city, region, country = _split_location(location)
    business_category = normalize_text(intent.business_category)
    query = normalize_text(intent.search_query)
    return {
        "business_category": business_category,
        "business_slug": _slug(business_category),
        "category": business_category,
        "category_slug": _slug(str(source_config.get("category_slug") or business_category)),
        "city": city,
        "city_slug": _slug(city),
        "region": region,
        "region_slug": _slug(region),
        "country": country or normalize_text(intent.country) or product.target_geography,
        "country_slug": _slug(country or normalize_text(intent.country) or product.target_geography),
        "location": location,
        "location_slug": _slug(location),
        "location_code": source_config.get("location_code") or "",
        "query": query,
        "query_slug": _slug(query),
        "limit": request.max_results,
        "max_results": request.max_results,
        "source_url": intent.search_url or "",
        "original_prompt": request.prompt,
    }


def _render_search_recipe(
    recipe: dict[str, Any],
    *,
    intent: SourceRequestIntent,
    product: ProductRead,
) -> str:
    location = normalize_text(intent.location)
    city, region, country = _split_location(location)
    values = {
        "business_category": normalize_text(intent.business_category),
        "category": normalize_text(intent.business_category),
        "location": location,
        "city": city,
        "region": region,
        "country": country or normalize_text(intent.country) or product.target_geography,
        "query": normalize_text(intent.search_query),
        "domain": normalize_text(recipe.get("domain")),
    }
    return normalize_text(_render_template(str(recipe.get("query_template") or ""), values))


def _deterministic_request_scope(
    *,
    prompt: str,
    explicit_category: str | None,
    explicit_geography: str | None,
    default_category: str,
    default_geography: str,
) -> tuple[str, str]:
    normalized = normalize_text(prompt)
    category_part = normalized
    location_part = ""
    match = re.match(r"^(?P<category>.+?)\s+in\s+(?P<location>.+)$", normalized, flags=re.I)
    if match:
        category_part = normalize_text(match.group("category"))
        location_part = normalize_text(match.group("location"))
    category = normalize_text(explicit_category) or _clean_category(category_part)
    location = normalize_text(explicit_geography) or _clean_location(location_part)
    if not category:
        category = _clean_category(default_category) or "local businesses"
    if not location:
        location = normalize_text(default_geography)
    if not location:
        raise ValidationError(
            "search request needs a geography",
            {"user_message": "Add a city or region to the search."},
        )
    return category, location


def _clean_category(value: str) -> str:
    cleaned = _REQUEST_PREFIX_RE.sub("", normalize_text(value))
    cleaned = re.sub(
        r"\b(?:contact|lead)\s+(?:details|information|info)\b",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = _CONTACT_SUFFIX_RE.sub("", cleaned)
    return normalize_text(cleaned.strip(" ,.-"))


def _clean_location(value: str) -> str:
    cleaned = _REQUEST_QUALIFIER_RE.sub("", normalize_text(value))
    return normalize_text(cleaned.strip(" ,.-"))


def _required_signals(prompt: str) -> list[str]:
    lower = prompt.lower()
    signals = []
    if any(term in lower for term in ("no website", "without a website", "missing website")):
        signals.append("no website")
    if any(term in lower for term in ("dead website", "inactive website", "broken website")):
        signals.append("unavailable website")
    if "phone" in lower:
        signals.append("phone")
    if "email" in lower:
        signals.append("email")
    return signals


def _country_hint(value: str) -> str:
    lower = value.lower()
    if "canada" in lower or re.search(r"\b(?:on|bc|ab|qc|mb|sk|ns|nb|nl|pe)\b", lower):
        return "Canada"
    if "united states" in lower or " usa" in f" {lower}" or re.search(r"\b[A-Z]{2}\b", value):
        return "United States"
    return ""


def _split_location(location: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in location.split(",") if part.strip()]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1], ""
    tokens = location.split()
    if len(tokens) >= 2 and len(tokens[-1]) in {2, 3}:
        return " ".join(tokens[:-1]), tokens[-1], ""
    return location, "", ""


def _render_template(value: Any, values: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render_template(child, values) for key, child in value.items()}
    if isinstance(value, list):
        return [_render_template(child, values) for child in value]
    if isinstance(value, str):
        match = re.fullmatch(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", value)
        if match:
            return values.get(match.group(1), "")
        rendered = value
        for key, replacement in values.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(replacement))
            rendered = rendered.replace(f"{{{{ {key} }}}}", str(replacement))
        return rendered
    return value


def _slug(value: str) -> str:
    normalized = normalize_text(value).lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return truncate(normalized.strip("-"), 120)
