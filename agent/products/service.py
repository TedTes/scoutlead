from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlparse

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from agents.llm import LLMClient
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
    ProductInferenceRead,
    ProductRead,
    ProductSourceCreate,
    ProductSourceEvidence,
    ProductUpdate,
    QualificationCriterion,
)
from shared.errors import ValidationError
from shared.logger import get_logger
from shared.utils import normalize_text, truncate, utcnow
from tools.browser import DirectHttpBrowserTool, WebsiteInspection
from tools.search import SearchResult, SearchTool

logger = get_logger(__name__)


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
        target_customer = self._target_customer_from_description(description, name)
        problem = self._problem_from_description(description, target_customer)
        value = self._value_from_description(description, target_customer, name)
        queries = self._fallback_queries(
            description,
            target_customer,
            request.target_geography,
            description,
        )
        return ProductCreate(
            product_name=name,
            product_description=description,
            target_customer=target_customer,
            problem_being_solved=problem,
            value_proposition=value,
            target_geography=request.target_geography,
            validation_goal=f"Book customer discovery interviews with {target_customer.lower()}.",
            qualification_criteria=[
                QualificationCriterion(
                    label=f"Matches target customer: {target_customer}",
                    weight=3,
                    required=True,
                    evidence_required=True,
                ),
                QualificationCriterion(
                    label="Shows a public signal related to the described workflow",
                    weight=2,
                    required=False,
                    evidence_required=True,
                ),
                QualificationCriterion(
                    label="Has reachable contact information",
                    weight=1,
                    required=False,
                    evidence_required=True,
                ),
            ],
            preferred_discovery_sources=[
                DiscoverySource(type=DiscoverySourceType.WEB_SEARCH, value=query, limit=10)
                for query in queries
            ],
            outreach_objective="Ask for a short customer discovery conversation.",
            constraints=[
                "Human approval required before outbound messages are sent.",
                "Position outreach as customer discovery, not a product pitch.",
            ],
            source_evidence={
                "source": "user_description",
                "description": description,
            },
        )

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

        cached_base = self.products.find_latest_source_draft(
            source_fingerprint=source_cache_fingerprint
        )
        if context and cached_base is not None:
            inference = self._refine_cached_source_draft(
                source=source,
                context=context,
                target_geography=request.target_geography,
                source_url=source_url,
                source_fingerprint=source_fingerprint,
                cached=ProductInferenceRead.model_validate(cached_base.inference),
            )
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

        inspection = self._inspect_source(source)
        lookup_results: list[SearchResult] = []
        if not self._has_enough_source_evidence(inspection) and source_url:
            lookup_results = self._lookup_source_results(source_url)
            inspection = self._merge_lookup_results(inspection, source_url, lookup_results)
        fallback_evidence = self._fallback_evidence(source, context, inspection)
        fallback = self._fallback_product(
            source,
            request.target_geography,
            inspection,
            context,
            fallback_evidence,
        )
        fallback = self._attach_source_metadata(
            fallback,
            source_url=source_url,
            source_fingerprint=source_fingerprint,
            evidence=fallback_evidence,
        )
        if self.llm is None or not self._has_enough_source_evidence(inspection, context):
            inference = self._build_inference(source, context, fallback_evidence, fallback)
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

        try:
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
                fallback=fallback_evidence,
            )
        except PydanticValidationError as exc:
            logger.warning("invalid_product_source_evidence error=%s", exc)
            evidence = fallback_evidence
        evidence = self._stabilize_context_evidence(evidence, fallback_evidence, context)

        draft_fallback = self._fallback_product(
            source,
            request.target_geography,
            inspection,
            context,
            evidence,
        )
        try:
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
                fallback=draft_fallback,
            )
        except PydanticValidationError as exc:
            logger.warning("invalid_product_config_from_evidence error=%s", exc)
            draft = draft_fallback
        draft = self._reject_ungrounded_inference(draft, draft_fallback, inspection, context)
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
    def _fallback_evidence(
        source: str,
        context: str | None,
        inspection: WebsiteInspection | None,
    ) -> ProductSourceEvidence:
        snippets: list[str] = []
        if inspection and inspection.title:
            snippets.append(f"Title: {inspection.title}")
        if inspection and inspection.description:
            snippets.append(f"Description: {inspection.description}")
        if inspection and inspection.text:
            snippets.append(f"Page text: {truncate(normalize_text(inspection.text), 280)}")
        if context:
            snippets.append(f"User context: {context}")

        confidence = ProductService._fallback_evidence_confidence(context, inspection)
        missing_info = []
        if confidence < 70:
            missing_info = [
                "Add one sentence describing what the product does.",
                "Add who the product is for.",
                "Add the main customer problem or workflow it improves.",
            ]
        return ProductSourceEvidence(
            product_name_candidates=[
                ProductService._fallback_name(source, inspection),
            ],
            headline=inspection.title if inspection and inspection.title else None,
            claims=[inspection.description] if inspection and inspection.description else [],
            target_customer_clues=[],
            problem_clues=[],
            value_clues=[],
            source_snippets=snippets[:6],
            confidence=confidence,
            missing_info=missing_info,
            rationale=(
                "Grounded in submitted source and optional user context."
                if confidence >= 70
                else "The submitted source is too sparse or ambiguous for reliable product inference."
            ),
        )

    @staticmethod
    def _fallback_evidence_confidence(
        context: str | None,
        inspection: WebsiteInspection | None,
    ) -> int:
        context_words = len(re.findall(r"[A-Za-z]{3,}", context or ""))
        source_words = len(re.findall(r"[A-Za-z]{3,}", ProductService._source_evidence_text(inspection)))
        if context_words >= 6 and source_words >= 18:
            return 82
        if context_words >= 6:
            return 74
        if source_words >= 60:
            return 72
        if source_words >= 18:
            return 72
        if inspection and (inspection.title or inspection.description):
            return 35
        return 20

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

    def _refine_cached_source_draft(
        self,
        *,
        source: str,
        context: str,
        target_geography: str,
        source_url: str | None,
        source_fingerprint: str | None,
        cached: ProductInferenceRead,
    ) -> ProductInferenceRead:
        evidence = self._contextualize_evidence(cached.evidence, context)
        inspection = WebsiteInspection(
            url=source_url or cached.product.source_url or source,
            title=cached.product.product_name,
            description=cached.product.product_description,
            text=truncate(
                normalize_text(
                    " ".join(
                        [
                            cached.product.product_description,
                            cached.product.target_customer,
                            cached.product.problem_being_solved,
                            cached.product.value_proposition,
                            " ".join(cached.evidence.source_snippets),
                            context,
                        ]
                    )
                ),
                10000,
            ),
        )
        product = self._fallback_product(
            source,
            target_geography,
            inspection,
            context,
            evidence,
        )
        product = self._attach_source_metadata(
            product,
            source_url=source_url,
            source_fingerprint=source_fingerprint,
            evidence=evidence,
        )
        return self._build_inference(source, context, evidence, product)

    @staticmethod
    def _contextualize_evidence(
        evidence: ProductSourceEvidence,
        context: str,
    ) -> ProductSourceEvidence:
        context_words = len(re.findall(r"[A-Za-z]{3,}", context))
        confidence = evidence.confidence
        missing_info = evidence.missing_info
        if context_words >= 6:
            confidence = max(confidence, 82 if evidence.confidence >= 50 else 74)
            if confidence >= 70:
                missing_info = []
        snippets = ProductService._dedupe_snippets(
            [*evidence.source_snippets, f"User context: {context}"]
        )
        return evidence.model_copy(
            update={
                "confidence": confidence,
                "missing_info": missing_info,
                "source_snippets": snippets[:6],
                "rationale": "Cached source evidence was reused and strengthened with user context.",
            }
        )

    @staticmethod
    def _stabilize_context_evidence(
        evidence: ProductSourceEvidence,
        fallback: ProductSourceEvidence,
        context: str | None,
    ) -> ProductSourceEvidence:
        if not context or evidence.confidence >= fallback.confidence:
            return evidence
        snippets = ProductService._dedupe_snippets(
            [*fallback.source_snippets, *evidence.source_snippets]
        )
        return fallback.model_copy(
            update={
                "confidence": fallback.confidence,
                "missing_info": fallback.missing_info,
                "source_snippets": snippets[:6],
                "rationale": (
                    "LLM evidence scored lower after context was added, so the grounded "
                    "source and user-context fallback was kept."
                ),
            }
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
    def _reject_ungrounded_inference(
        inferred: ProductCreate,
        fallback: ProductCreate,
        inspection: WebsiteInspection | None,
        context: str | None = None,
    ) -> ProductCreate:
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
            return fallback
        return inferred

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

    @staticmethod
    def _target_customer_from_description(description: str, product_name: str) -> str:
        target_customer = ProductService._target_customer_from_text(description, product_name)
        if target_customer:
            return target_customer
        return f"Customers likely to benefit from {product_name}"

    @staticmethod
    def _target_customer_from_text(text: str, product_name: str) -> str | None:
        text = normalize_text(text)
        patterns = [
            r"\b(?:helps|serves|supports)\s+(.+?)\s+(?:capture|send|manage|book|find|create|track|automate|replace|coordinate|validate|generate|reduce|improve|handle|compare|discover|qualify|draft|sync|run|save|centralize|organize|build|collect|turn|get|close)\b",
            r"\b(?:for|built for|made for)\s+(.+?)(?:\s+(?:who|that|to|with|by|using|needing)\b|[.,;]|$)",
            r"\b(?:used by|serving|serve)\s+(.+?)(?:\s+(?:who|that|to|with|by|using|needing)\b|[.,;]|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip(" ,.-")
                if candidate and product_name.lower() not in candidate.lower():
                    return truncate(candidate, 140)
        return None

    @staticmethod
    def _problem_from_description(description: str, target_customer: str) -> str:
        text = normalize_text(description)
        explicit_problem = re.search(
            r"\b(?:problem|pain|challenge)\s*(?:is|:|-)\s*(.+?)(?:\.|$)",
            text,
            flags=re.IGNORECASE,
        )
        if explicit_problem:
            return truncate(explicit_problem.group(1).strip(), 220)
        if any(keyword in text.lower() for keyword in ["quote", "estimate", "proposal"]):
            return f"{target_customer} need a faster and more consistent quote workflow."
        return f"{target_customer} have a workflow that may be slow, manual, or inconsistent."

    @staticmethod
    def _value_from_description(
        description: str,
        target_customer: str,
        product_name: str,
    ) -> str:
        text = normalize_text(description)
        value_match = re.search(
            r"\b(?:helps|lets|enables|allows)\s+.+?\s+(?:to\s+)?(.+?)(?:\.|$)",
            text,
            flags=re.IGNORECASE,
        )
        if value_match:
            return truncate(f"Help {target_customer} {value_match.group(1).strip()}.", 220)
        return truncate(f"Help {target_customer} solve the workflow described for {product_name}.", 220)

    def _fallback_product(
        self,
        source: str,
        target_geography: str,
        inspection: WebsiteInspection | None,
        context: str | None = None,
        evidence: ProductSourceEvidence | None = None,
    ) -> ProductCreate:
        name = (
            evidence.product_name_candidates[0].strip()
            if evidence and evidence.product_name_candidates and evidence.product_name_candidates[0].strip()
            else self._fallback_name(source, inspection)
        )
        text = ". ".join(
            filter(
                None,
                [
                    context,
                    inspection.title if inspection else None,
                    inspection.description if inspection else None,
                    inspection.text if inspection else None,
                    source,
                ],
            )
        )
        target_customer = self._fallback_target_customer(text, name)
        if evidence and evidence.confidence < 70 and not context:
            return ProductCreate(
                product_name=name,
                product_description=(
                    f"{name} could not be identified from the submitted source."
                ),
                target_customer="Unknown until more product context is provided",
                problem_being_solved=(
                    "Not enough public source evidence to identify the customer problem."
                ),
                value_proposition=(
                    "Not enough public source evidence to identify the value proposition."
                ),
                target_geography=target_geography,
                validation_goal="Add product context before running customer discovery.",
                qualification_criteria=[
                    QualificationCriterion(
                        label="Product context is available",
                        weight=1,
                        required=True,
                        evidence_required=True,
                    )
                ],
                preferred_discovery_sources=[
                    DiscoverySource(
                        type=DiscoverySourceType.WEB_SEARCH,
                        value="Add product context before running discovery",
                        limit=1,
                    )
                ],
                outreach_objective="Add product context before drafting outreach.",
                constraints=[
                    "Human approval required before outbound messages are sent.",
                    "Do not run discovery until product context is available.",
                ],
            )
        product_description = (
            context
            if context
            else inspection.description
            if inspection and inspection.description
            else truncate(normalize_text(inspection.text), 240)
            if inspection and inspection.text
            else f"{name} is a product being validated from the provided source."
        )
        product_description = truncate(normalize_text(product_description), 280)
        problem = self._fallback_problem(text, target_customer)
        value = self._fallback_value(name, product_description)
        queries = self._fallback_queries(source, target_customer, target_geography, text)
        return ProductCreate(
            product_name=name,
            product_description=product_description,
            target_customer=target_customer,
            problem_being_solved=problem,
            value_proposition=value,
            target_geography=target_geography,
            validation_goal=f"Book customer discovery interviews with {target_customer.lower()}.",
            qualification_criteria=[
                QualificationCriterion(
                    label=f"Matches target customer: {target_customer}",
                    weight=3,
                    required=True,
                    evidence_required=True,
                ),
                QualificationCriterion(
                    label="Shows a public signal related to the problem",
                    weight=2,
                    required=False,
                    evidence_required=True,
                ),
                QualificationCriterion(
                    label="Has reachable contact information",
                    weight=1,
                    required=False,
                    evidence_required=True,
                ),
            ],
            preferred_discovery_sources=[
                DiscoverySource(type=DiscoverySourceType.WEB_SEARCH, value=query, limit=10)
                for query in queries
            ],
            outreach_objective="Ask for a short customer discovery conversation.",
            constraints=[
                "Human approval required before outbound messages are sent.",
                "Position outreach as customer discovery, not a product pitch.",
            ],
        )

    @staticmethod
    def _fallback_name(source: str, inspection: WebsiteInspection | None) -> str:
        title = inspection.title if inspection and inspection.title else ""
        if title:
            return re.split(r"\s[|–—-]\s", title, maxsplit=1)[0].strip()[:80] or "New Product"
        parsed = urlparse(ProductService._source_url(source) or "")
        host = parsed.netloc.replace("www.", "")
        if host:
            return host.split(".")[0].replace("-", " ").title()
        return source.splitlines()[0].strip()[:80] or "New Product"

    @staticmethod
    def _fallback_target_customer(text: str, product_name: str) -> str:
        target_customer = ProductService._target_customer_from_text(text, product_name)
        if target_customer:
            return target_customer
        lower = text.lower()
        if any(keyword in lower for keyword in ["quote", "estimate", "invoice"]):
            return "Service businesses that handle quote requests"
        return f"Businesses likely to benefit from {product_name}"

    @staticmethod
    def _fallback_problem(text: str, target_customer: str) -> str:
        lower = text.lower()
        if any(keyword in lower for keyword in ["quote", "estimate"]):
            return f"{target_customer} lose opportunities when quote requests are slow or inconsistent."
        return f"{target_customer} need a clearer workflow for the problem this product addresses."

    @staticmethod
    def _fallback_value(product_name: str, description: str) -> str:
        if description:
            return truncate(description, 140)
        return f"Help customers validate whether {product_name} solves an urgent workflow problem."

    @staticmethod
    def _fallback_queries(source: str, target_customer: str, geography: str, text: str) -> list[str]:
        if " " in source and "." not in source:
            return [source]
        return [
            f"{target_customer} {geography}",
            f"{target_customer} contact {geography}",
            f"{target_customer} business owner {geography}",
        ]
