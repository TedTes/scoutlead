from __future__ import annotations

import re
from typing import Any

from agents.llm import LLMClient
from products.discovery_policy import normalize_places_region_code, validate_google_places_query
from products.schemas import ProductRead
from prompts.source_intent import SOURCE_INTENT_PROMPT, SOURCE_INTENT_SYSTEM
from shared.errors import ValidationError
from shared.utils import normalize_text, truncate
from source_requests.schemas import (
    GOOGLE_PLACES_PROVIDER_ID,
    SourceProviderKind,
    SourceRequestAction,
    SourceRequestCreate,
    SourceRequestIntent,
    SourceRequestPlan,
)


URL_INPUT_KINDS = {
    SourceProviderKind.URL_LIST.value,
    SourceProviderKind.SEARCH_URL.value,
    SourceProviderKind.CLASSIFIED_SEARCH_URL.value,
}


class SourceRequestCompiler:
    def __init__(self, *, llm: LLMClient) -> None:
        self.llm = llm

    def compile_google_places(
        self,
        *,
        request: SourceRequestCreate,
        product: ProductRead,
    ) -> SourceRequestPlan:
        intent = self._interpret(request=request, product=product, source=GOOGLE_PLACES_PROVIDER_ID)
        query = normalize_text(intent.search_query)
        validate_google_places_query(query)
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
                "region_code": region_code,
                "compiled_provider_input": {
                    "textQuery": query,
                    "pageSize": request.max_results,
                    "regionCode": region_code,
                },
            },
        )

    def compile_apify_source(
        self,
        *,
        request: SourceRequestCreate,
        product: ProductRead,
        source_config: dict[str, Any],
    ) -> SourceRequestPlan:
        source_id = str(source_config.get("id") or request.source).strip()
        source_label = str(source_config.get("label") or source_id)
        intent = self._interpret(request=request, product=product, source=source_id)
        values = _template_values(
            request=request,
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
        )

    def _interpret(
        self,
        *,
        request: SourceRequestCreate,
        product: ProductRead,
        source: str,
    ) -> SourceRequestIntent:
        prompt = "\n".join(
            [
                SOURCE_INTENT_PROMPT,
                f"Source: {source}",
                f"Request: {request.prompt}",
                f"Product: {product.model_dump(mode='json')}",
            ]
        )
        return self.llm.generate_object(
            task="source_request_intent",
            system=SOURCE_INTENT_SYSTEM,
            prompt=prompt,
            response_model=SourceRequestIntent,
            context={
                "source": source,
                "request": request.model_dump(mode="json"),
                "product": product.model_dump(mode="json"),
            },
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
