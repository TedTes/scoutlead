from __future__ import annotations

import hashlib
import json

from agents.llm import LLMClient
from business_index.contracts import fact_catalog_for_prompt
from products.schemas import ProductRead
from shared.errors import ValidationError
from shared.utils import normalize_text
from source_requests.schemas import SourceRequestCreate, SourceRequestIntent


SEARCH_INTENT_SCHEMA_VERSION = 1


class SearchIntentInterpreter:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def interpret(
        self,
        *,
        request: SourceRequestCreate,
        product: ProductRead,
    ) -> SourceRequestIntent:
        interpreted = self.llm.generate_object(
            task="search_intent_compile",
            system=(
                "Translate a flexible lead-search request into the supplied structured schema. "
                "The user's request has priority over product defaults. Preserve nuanced criteria "
                "as plain-language criteria with fact_key=null. Use a fact_key only when the "
                "criterion exactly matches a supported fact definition. Do not invent facts, "
                "business categories, locations, thresholds, or exclusions. Put every condition "
                "that decides whether a business is returned in criteria. Group required, "
                "alternative, and excluded criteria using the criterion mode. Use required_signals "
                "and excluded_result_types only as source-discovery hints, not as substitutes for criteria."
            ),
            prompt=request.prompt,
            response_model=SourceRequestIntent,
            context={
                "request": request.model_dump(mode="json", exclude={"intent_override"}),
                "product": product.model_dump(mode="json"),
                "supported_facts": fact_catalog_for_prompt(),
                "supported_contact_requirements": [
                    "email",
                    "phone",
                    "website",
                    "any_contact",
                ],
                "schema_version": SEARCH_INTENT_SCHEMA_VERSION,
            },
        )
        return normalize_search_intent(
            interpreted,
            explicit_category=request.business_category,
            explicit_geography=request.geography,
        )


def normalize_search_intent(
    intent: SourceRequestIntent,
    *,
    explicit_category: str | None = None,
    explicit_geography: str | None = None,
) -> SourceRequestIntent:
    category = normalize_text(explicit_category) or normalize_text(intent.business_category)
    location = normalize_text(explicit_geography) or normalize_text(intent.location)
    if not category:
        raise ValidationError(
            "search intent needs a business category",
            {"user_message": "Describe the type of business to find."},
        )
    if not location:
        raise ValidationError(
            "search intent needs a geography",
            {"user_message": "Add a city or region to the search."},
        )
    return intent.model_copy(
        update={
            "schema_version": SEARCH_INTENT_SCHEMA_VERSION,
            "business_category": category,
            "location": location,
            "included_subcategories": _clean_values(intent.included_subcategories),
            "criteria": intent.criteria[:12],
            "contact_requirements": _clean_values(intent.contact_requirements),
            "required_signals": _clean_values(intent.required_signals),
            "excluded_result_types": _clean_values(intent.excluded_result_types),
            "search_query": normalize_text(f"{category} in {location}"),
        }
    )


def search_intent_request_hash(request: SourceRequestCreate) -> str:
    payload = {
        "schema_version": SEARCH_INTENT_SCHEMA_VERSION,
        "product_id": request.product_id,
        "prompt": normalize_text(request.prompt).casefold(),
        "business_category": normalize_text(request.business_category).casefold(),
        "geography": normalize_text(request.geography).casefold(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _clean_values(values: list[str]) -> list[str]:
    return list(dict.fromkeys(normalize_text(value) for value in values if normalize_text(value)))
