from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlparse

from sqlalchemy.orm import Session

from agents.llm import LLMClient
from prompts.discovery_plan import DISCOVERY_PLAN_PROMPT, DISCOVERY_PLAN_SYSTEM
from db.models import ProductModel
from prompts.product_inference import (
    PRODUCT_CONFIG_PROMPT,
    PRODUCT_CONFIG_SYSTEM,
    PRODUCT_EVIDENCE_PROMPT,
    PRODUCT_EVIDENCE_SYSTEM,
)
from products.repository import ProductRepository
from products.schemas import (
    DiscoverySource,
    DiscoverySourceType,
    ProductCreate,
    ProductDescriptionCreate,
    ProductDiscoveryPlan,
    ProductInferenceRead,
    ProductRead,
    ProductSourceCreate,
    ProductSourceEvidence,
    ProductUpdate,
)
from shared.errors import ConfigurationError, ValidationError
from shared.utils import normalize_text, truncate, utcnow
from tools.browser import DirectHttpBrowserTool, WebsiteInspection
from tools.search import SearchResult, SearchTool


class ProductService:
    def __init__(
        self,
        session: Session,
        *,
        llm: LLMClient | None = None,
        browser: DirectHttpBrowserTool | None = None,
        search: SearchTool | None = None,
    ) -> None:
        self.products = ProductRepository(session)
        self.llm = llm
        self.browser = browser
        self.search = search

    def create(self, product: ProductCreate) -> ProductModel:
        return self.products.create(product)

    def create_from_description(self, request: ProductDescriptionCreate) -> ProductModel:
        return self.products.create(self.product_from_description(request))

    def product_from_description(self, request: ProductDescriptionCreate) -> ProductCreate:
        description = normalize_text(request.description)
        if len(description) < 20:
            raise ValidationError(
                "product description is too short",
                {"minimum_length": 20},
            )
        name = normalize_text(request.product_name)
        target_geography = normalize_text(request.target_geography) or "United States, Canada"
        return ProductCreate(
            product_name=name,
            product_description=description,
            target_customer="Define target customer before running discovery.",
            problem_being_solved="Define the customer problem before running discovery.",
            value_proposition="Define the value proposition before running discovery.",
            target_geography=target_geography,
            validation_goal="Book customer discovery interviews.",
            qualification_criteria=[
                {
                    "label": "Target customer fit needs setup",
                    "description": "Replace this draft criterion with public signals for the intended ICP.",
                    "weight": 1,
                    "required": True,
                    "evidence_required": True,
                }
            ],
            preferred_discovery_sources=[],
            outreach_objective="Ask for a short customer discovery conversation.",
            constraints=["Human approval required before outbound messages are sent."],
            source_url=None,
            source_fingerprint=None,
            source_last_checked_at=None,
            source_evidence={
                "source": "user_description",
                "description": description,
                "config_generated_by": "deterministic_draft",
                "profile_status": "draft",
            },
        )

    @staticmethod
    def _normalize_description_product(
        product: ProductCreate,
        *,
        name: str,
        description: str,
        target_geography: str,
    ) -> ProductCreate:
        data = product.model_dump(mode="json")
        data["product_name"] = name
        data["target_geography"] = target_geography
        data["source_url"] = None
        data["source_fingerprint"] = None
        data["source_last_checked_at"] = None
        evidence = data.get("source_evidence") if isinstance(data.get("source_evidence"), dict) else {}
        evidence.update(
            {
                "source": "user_description",
                "description": description,
                "config_generated_by": "llm",
            }
        )
        data["source_evidence"] = evidence
        if not data.get("constraints"):
            data["constraints"] = []
        if not any(
            "human approval" in constraint.lower()
            for constraint in data["constraints"]
            if isinstance(constraint, str)
        ):
            data["constraints"].append("Human approval required before outbound messages are sent.")
        return ProductCreate.model_validate(data)

    def create_from_source(self, request: ProductSourceCreate) -> ProductModel:
        inference = self.infer_product_from_source(request)
        if inference.existing_product is not None:
            return self.products.get(inference.existing_product.id)
        if not inference.ready_to_save:
            raise ValidationError(
                "source does not contain enough product evidence to create a product",
                {
                    "confidence": inference.confidence,
                    "missing_info": inference.missing_info,
                },
            )
        return self.products.create(inference.product)

    def infer_from_source(self, request: ProductSourceCreate) -> ProductCreate:
        return self.infer_product_from_source(request).product

    def infer_product_from_source(self, request: ProductSourceCreate) -> ProductInferenceRead:
        source = request.source.strip()
        context = request.context.strip() if request.context else None
        source_url = self._normalized_source_url(source)
        source_fingerprint = self._source_fingerprint(source_url)
        source_cache_fingerprint = self._source_cache_fingerprint(source, source_url)
        context_fingerprint = self._context_fingerprint(context)
        existing = self.products.find_by_source_fingerprint(source_fingerprint)
        if existing is None and source_url and source_fingerprint:
            legacy_match = self.products.find_active_by_product_name(
                self._source_product_name_hint(source_url)
            )
            if legacy_match is not None and not legacy_match.source_fingerprint:
                existing = self.products.attach_source_metadata(
                    legacy_match.id,
                    source_url=source_url,
                    source_fingerprint=source_fingerprint,
                )
        if existing is not None:
            return self._existing_product_inference(source, context, ProductRead.model_validate(existing))

        cached = self.products.find_source_draft(
            source_fingerprint=source_cache_fingerprint,
            context_fingerprint=context_fingerprint,
        )
        if cached is not None:
            return ProductInferenceRead.model_validate(cached.inference)

        inspection = self._inspect_source(source)
        lookup_results: list[SearchResult] = []
        if not self._has_enough_source_evidence(inspection) and source_url:
            lookup_results = self._lookup_source_results(source_url)
            inspection = self._merge_lookup_results(inspection, source_url, lookup_results)
        if self.llm is None:
            raise ConfigurationError(
                "LLM provider is required to infer a product profile from source content",
                {"task": "product_source_evidence"},
            )
        if not self._has_enough_source_evidence(inspection, context):
            raise ValidationError(
                "source does not contain enough product evidence",
                {
                    "source": source,
                    "missing_info": [
                        "Add a product description with the target customer, problem, and value proposition."
                    ],
                },
            )

        evidence = self.llm.generate_object(
            task="product_source_evidence",
            system=PRODUCT_EVIDENCE_SYSTEM,
            prompt=PRODUCT_EVIDENCE_PROMPT,
            response_model=ProductSourceEvidence,
            context={
                "source": source,
                "user_context": context,
                "target_geography": request.target_geography,
                "website": inspection.model_dump(mode="json") if inspection else None,
                "source_lookup_results": [
                    result.model_dump(mode="json") for result in lookup_results
                ],
            },
        )
        if evidence.confidence < 70 or evidence.missing_info:
            raise ValidationError(
                "source evidence is not strong enough to create a product profile",
                {
                    "confidence": evidence.confidence,
                    "missing_info": evidence.missing_info,
                    "rationale": evidence.rationale,
                },
            )

        draft = self.llm.generate_object(
            task="product_config_from_evidence",
            system=PRODUCT_CONFIG_SYSTEM,
            prompt=PRODUCT_CONFIG_PROMPT,
            response_model=ProductCreate,
            context={
                "source": source,
                "user_context": context,
                "target_geography": request.target_geography,
                "evidence": evidence.model_dump(mode="json"),
                "website": inspection.model_dump(mode="json") if inspection else None,
                "source_lookup_results": [
                    result.model_dump(mode="json") for result in lookup_results
                ],
            },
        )
        self._assert_grounded_inference(draft, inspection, context)
        draft = self._attach_source_metadata(
            draft,
            source_url=source_url,
            source_fingerprint=source_fingerprint,
            evidence=evidence,
        )
        inference = self._build_inference(source, context, evidence, draft)
        self._cache_source_draft(
            source=source,
            source_url=source_url,
            source_cache_fingerprint=source_cache_fingerprint,
            context=context,
            context_fingerprint=context_fingerprint,
            target_geography=request.target_geography,
            inference=inference,
        )
        return inference

    def list(self) -> list[ProductModel]:
        return self.products.list()

    def get(self, product_id: str) -> ProductModel:
        return self.products.get(product_id)

    def update(self, product_id: str, update: ProductUpdate) -> ProductModel:
        return self.products.update(product_id, update)

    def delete(self, product_id: str) -> None:
        self.products.delete(product_id)

    def plan_discovery(self, product_id: str) -> ProductDiscoveryPlan:
        if self.llm is None:
            raise ConfigurationError(
                "LLM provider is required to plan discovery from a product description",
                {"task": "product_discovery_plan"},
            )
        product = ProductRead.model_validate(self.products.get(product_id))
        plan = self.llm.generate_object(
            task="product_discovery_plan",
            system=DISCOVERY_PLAN_SYSTEM,
            prompt=DISCOVERY_PLAN_PROMPT,
            response_model=ProductDiscoveryPlan,
            context={
                "product_name": product.product_name,
                "product_description": product.product_description,
                "existing_target_geography": product.target_geography,
            },
        )
        return plan.model_copy(
            update={
                "product_name": product.product_name,
                "product_description": product.product_description,
            }
        )

    def apply_discovery_plan(self, product_id: str, plan: ProductDiscoveryPlan) -> ProductModel:
        return self.products.update(
            product_id,
            ProductUpdate(
                target_customer=plan.target_customer,
                problem_being_solved=plan.problem_being_solved,
                value_proposition=plan.value_proposition,
                target_geography=plan.target_geography,
                validation_goal=plan.validation_goal,
                qualification_criteria=plan.qualification_criteria,
                preferred_discovery_sources=[
                    DiscoverySource(
                        type=DiscoverySourceType.WEB_SEARCH,
                        value=plan.discovery_query,
                    )
                ],
                outreach_objective=plan.outreach_objective,
                constraints=["Human approval required before outbound messages are sent."],
                source_evidence={
                    "source": "product_description_discovery_plan",
                    "rationale": plan.rationale,
                    "source_provider": "google_places",
                    "source_provider_selected_by": "application_policy",
                    "region_code": plan.region_code,
                },
            ),
        )

    def _inspect_source(self, source: str) -> WebsiteInspection | None:
        if self.browser is None:
            return None
        url = self._source_url(source)
        if url is None:
            return None
        root = self.browser.inspect(url)
        if root.error:
            return root

        inspections = [root]
        for link in self._candidate_detail_links(root):
            inspections.append(self.browser.inspect(link))

        text_parts: list[str] = []
        emails: list[str] = []
        links: list[str] = []
        for inspection in inspections:
            if inspection.error:
                continue
            title = inspection.title or ""
            description = inspection.description or ""
            text = inspection.text or ""
            text_parts.append(
                normalize_text(
                    " ".join(part for part in [title, description, text] if part)
                )
            )
            emails.extend(inspection.emails)
            links.extend(inspection.links)

        return WebsiteInspection(
            url=root.url,
            title=root.title,
            description=root.description,
            text=truncate(normalize_text(" ".join(text_parts)), 10000),
            emails=sorted(set(emails))[:10],
            links=sorted(set(links))[:50],
        )

    def _lookup_source_results(self, source_url: str) -> list[SearchResult]:
        if self.search is None or not self.search.is_configured:
            return []
        host = urlparse(source_url).hostname or source_url
        name_hint = self._source_product_name_hint(source_url) or host
        queries = [
            f'"{host}" product',
            f'"{name_hint}" "{host}"',
            f'"{name_hint}" software product',
        ]
        results: list[SearchResult] = []
        seen_urls: set[str] = set()
        for query in queries:
            try:
                rows = self.search.lookup(query, limit=5)
            except Exception:
                continue
            for row in rows:
                if not self._lookup_result_matches_source(row, source_url):
                    continue
                key = row.url or row.title
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                results.append(row)
                if len(results) >= 5:
                    return results
        return results

    @staticmethod
    def _lookup_result_matches_source(result: SearchResult, source_url: str) -> bool:
        source_host = (urlparse(source_url).hostname or "").removeprefix("www.").lower()
        result_host = (urlparse(result.url or "").hostname or "").removeprefix("www.").lower()
        text = " ".join([result.title, result.snippet or "", result.url or ""]).lower()
        name_hint = ProductService._source_product_name_hint(source_url) or ""
        return (
            bool(source_host and result_host == source_host)
            or bool(source_host and source_host in text)
            or bool(name_hint and name_hint.lower() in text)
        )

    @staticmethod
    def _merge_lookup_results(
        inspection: WebsiteInspection | None,
        source_url: str,
        results: list[SearchResult],
    ) -> WebsiteInspection | None:
        if not results:
            return inspection
        lookup_text = " ".join(
            normalize_text(
                " ".join(
                    part
                    for part in [
                        f"Source lookup result: {result.title}",
                        result.snippet,
                        result.url,
                    ]
                    if part
                )
            )
            for result in results
        )
        if inspection is None:
            return WebsiteInspection(url=source_url, text=truncate(lookup_text, 10000))
        return inspection.model_copy(
            update={
                "text": truncate(
                    normalize_text(" ".join([inspection.text or "", lookup_text])),
                    10000,
                )
            }
        )

    @staticmethod
    def _candidate_detail_links(root: WebsiteInspection) -> list[str]:
        parsed_root = urlparse(root.url)
        root_host = parsed_root.netloc.replace("www.", "")
        keywords = [
            "about",
            "feature",
            "features",
            "product",
            "solution",
            "solutions",
            "pricing",
            "faq",
            "how-it-works",
        ]
        candidates: list[str] = []
        for link in root.links:
            absolute = urljoin(root.url, link).split("#", maxsplit=1)[0]
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            if parsed.netloc.replace("www.", "") != root_host:
                continue
            path = parsed.path.strip("/").lower()
            if not path or not any(keyword in path for keyword in keywords):
                continue
            if absolute not in candidates:
                candidates.append(absolute)
            if len(candidates) >= 3:
                break
        return candidates

    @staticmethod
    def _has_enough_source_evidence(
        inspection: WebsiteInspection | None,
        context: str | None = None,
    ) -> bool:
        if context and len(re.findall(r"[A-Za-z]{3,}", context)) >= 6:
            return True
        if inspection is None or inspection.error:
            return False
        evidence = ProductService._source_evidence_text(inspection)
        words = re.findall(r"[A-Za-z]{3,}", evidence)
        return len(words) >= 18

    @staticmethod
    def _source_evidence_text(inspection: WebsiteInspection | None) -> str:
        if inspection is None:
            return ""
        return normalize_text(
            " ".join(
                part
                for part in [inspection.title, inspection.description, inspection.text]
                if part
            )
        )

    @staticmethod
    def _build_inference(
        source: str,
        context: str | None,
        evidence: ProductSourceEvidence,
        product: ProductCreate,
        existing_product: ProductRead | None = None,
    ) -> ProductInferenceRead:
        ready_to_save = evidence.confidence >= 70 and not evidence.missing_info
        return ProductInferenceRead(
            source=source,
            context=context,
            ready_to_save=ready_to_save,
            confidence=evidence.confidence,
            missing_info=evidence.missing_info,
            evidence=evidence,
            product=product,
            existing_product=existing_product,
        )

    def _cache_source_draft(
        self,
        *,
        source: str,
        source_url: str | None,
        source_cache_fingerprint: str,
        context: str | None,
        context_fingerprint: str,
        target_geography: str,
        inference: ProductInferenceRead,
    ) -> None:
        self.products.upsert_source_draft(
            source=source,
            source_url=source_url,
            source_fingerprint=source_cache_fingerprint,
            context=context,
            context_fingerprint=context_fingerprint,
            target_geography=target_geography,
            inference=inference.model_dump(mode="json"),
        )

    @staticmethod
    def _dedupe_snippets(snippets: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for snippet in snippets:
            value = normalize_text(snippet)
            key = value.lower()
            if not value or key in seen:
                continue
            seen.add(key)
            deduped.append(value)
        return deduped

    @staticmethod
    def _existing_product_inference(
        source: str,
        context: str | None,
        existing_product: ProductRead,
    ) -> ProductInferenceRead:
        evidence = ProductService._existing_product_evidence(existing_product)
        product = ProductService._product_create_from_read(existing_product)
        return ProductService._build_inference(
            source,
            context,
            evidence,
            product,
            existing_product=existing_product,
        )

    @staticmethod
    def _existing_product_evidence(product: ProductRead) -> ProductSourceEvidence:
        if product.source_evidence:
            try:
                return ProductSourceEvidence.model_validate(product.source_evidence)
            except Exception:
                pass
        return ProductSourceEvidence(
            product_name_candidates=[product.product_name],
            headline=product.product_name,
            claims=[product.product_description],
            target_customer_clues=[product.target_customer],
            problem_clues=[product.problem_being_solved],
            value_clues=[product.value_proposition],
            source_snippets=[
                f"Existing saved product: {product.product_name}",
                f"Source URL: {product.source_url}",
            ],
            confidence=100,
            missing_info=[],
            rationale="Matched an existing saved product with the same normalized source URL.",
        )

    @staticmethod
    def _product_create_from_read(product: ProductRead) -> ProductCreate:
        return ProductCreate.model_validate(
            product.model_dump(
                mode="json",
                exclude={"id", "archived_at", "created_at", "updated_at"},
            )
        )

    @staticmethod
    def _attach_source_metadata(
        product: ProductCreate,
        *,
        source_url: str | None,
        source_fingerprint: str | None,
        evidence: ProductSourceEvidence,
    ) -> ProductCreate:
        if not source_url or not source_fingerprint:
            return product
        return product.model_copy(
            update={
                "source_url": source_url,
                "source_fingerprint": source_fingerprint,
                "source_last_checked_at": utcnow(),
                "source_evidence": evidence.model_dump(mode="json"),
            }
        )

    @staticmethod
    def _assert_grounded_inference(
        inferred: ProductCreate,
        inspection: WebsiteInspection | None,
        context: str | None = None,
    ) -> None:
        evidence = " ".join(
            [
                ProductService._source_evidence_text(inspection),
                context or "",
            ]
        ).lower()
        generated = " ".join(
            [
                inferred.product_description,
                inferred.target_customer,
                inferred.problem_being_solved,
                inferred.value_proposition,
                inferred.validation_goal,
                " ".join(source.value for source in inferred.preferred_discovery_sources),
            ]
        ).lower()
        ungrounded_phrases = [
            "van rental",
            "van rentals",
            "moving service",
            "moving services",
            "transportation",
            "delivery service",
            "delivery services",
        ]
        if any(phrase in generated and phrase not in evidence for phrase in ungrounded_phrases):
            raise ValidationError(
                "LLM product inference introduced unsupported product assumptions",
                {"unsupported_terms": ungrounded_phrases},
            )

    @staticmethod
    def _source_url(source: str) -> str | None:
        value = source.strip()
        if value.startswith(("http://", "https://")):
            return value
        if " " in value or "." not in value:
            return None
        return f"https://{value}"

    @staticmethod
    def _normalized_source_url(source: str) -> str | None:
        value = ProductService._source_url(source)
        if value is None:
            return None
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if not host:
            return None
        if host.startswith("www."):
            host = host.removeprefix("www.")
        try:
            port = parsed.port
        except ValueError:
            port = None
        netloc = f"{host}:{port}" if port else host
        path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/")
        return f"https://{netloc}{path}"

    @staticmethod
    def _source_fingerprint(source_url: str | None) -> str | None:
        if not source_url:
            return None
        return hashlib.sha256(source_url.encode("utf-8")).hexdigest()

    @staticmethod
    def _source_cache_fingerprint(source: str, source_url: str | None) -> str:
        normalized = source_url or normalize_text(source).lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _context_fingerprint(context: str | None) -> str:
        normalized = normalize_text(context or "").lower()
        if not normalized:
            return "no_context"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _source_product_name_hint(source_url: str) -> str | None:
        host = urlparse(source_url).hostname or ""
        first_label = host.split(".", maxsplit=1)[0]
        return first_label or None
