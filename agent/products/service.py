from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from agents.llm import LLMClient
from db.models import ProductModel
from products.repository import ProductRepository
from products.schemas import (
    DiscoverySource,
    DiscoverySourceType,
    ProductCreate,
    ProductSourceCreate,
    ProductUpdate,
    QualificationCriterion,
)
from shared.utils import normalize_text, truncate
from tools.browser import DirectHttpBrowserTool, WebsiteInspection


class ProductService:
    def __init__(
        self,
        session: Session,
        *,
        llm: LLMClient | None = None,
        browser: DirectHttpBrowserTool | None = None,
    ) -> None:
        self.products = ProductRepository(session)
        self.llm = llm
        self.browser = browser

    def create(self, product: ProductCreate) -> ProductModel:
        return self.products.create(product)

    def create_from_source(self, request: ProductSourceCreate) -> ProductModel:
        return self.products.create(self.infer_from_source(request))

    def infer_from_source(self, request: ProductSourceCreate) -> ProductCreate:
        source = request.source.strip()
        inspection = self._inspect_source(source)
        fallback = self._fallback_product(source, request.target_geography, inspection)
        if self.llm is None:
            return fallback

        return self.llm.generate_object(
            task="product_source_inference",
            system=(
                "You turn a product landing page or plain-language source into a complete "
                "customer discovery configuration. Infer the best target customer, problem, "
                "value proposition, validation goal, qualification criteria, and discovery "
                "search queries. Do not invent exact customer claims that are unsupported; "
                "use concise practical language for a validation campaign."
            ),
            prompt=(
                "Create a ProductCreate JSON object for ScoutLead. "
                "preferred_discovery_sources should contain 3-6 web_search queries that find "
                "potential customers, not searches for the product itself. "
                "qualification_criteria should be concrete public signals the workflow can verify."
            ),
            response_model=ProductCreate,
            context={
                "source": source,
                "target_geography": request.target_geography,
                "website": inspection.model_dump(mode="json") if inspection else None,
            },
            fallback=fallback,
        )

    def list(self) -> list[ProductModel]:
        return self.products.list()

    def get(self, product_id: str) -> ProductModel:
        return self.products.get(product_id)

    def update(self, product_id: str, update: ProductUpdate) -> ProductModel:
        return self.products.update(product_id, update)

    def _inspect_source(self, source: str) -> WebsiteInspection | None:
        if self.browser is None:
            return None
        url = self._source_url(source)
        if url is None:
            return None
        return self.browser.inspect(url)

    @staticmethod
    def _source_url(source: str) -> str | None:
        value = source.strip()
        if value.startswith(("http://", "https://")):
            return value
        if " " in value or "." not in value:
            return None
        return f"https://{value}"

    def _fallback_product(
        self,
        source: str,
        target_geography: str,
        inspection: WebsiteInspection | None,
    ) -> ProductCreate:
        name = self._fallback_name(source, inspection)
        text = " ".join(
            filter(
                None,
                [
                    inspection.title if inspection else None,
                    inspection.description if inspection else None,
                    inspection.text if inspection else None,
                    source,
                ],
            )
        )
        target_customer = self._fallback_target_customer(text, name)
        product_description = (
            inspection.description
            if inspection and inspection.description
            else truncate(normalize_text(inspection.text), 240)
            if inspection and inspection.text
            else f"{name} is a product being validated from the provided source."
        )
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
        lower = text.lower()
        if any(keyword in lower for keyword in ["paint", "painter", "painting", "contractor"]):
            return "Residential painting companies and small painting contractors"
        if any(keyword in lower for keyword in ["quote", "estimate", "invoice", "contractor"]):
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
        lower = text.lower()
        if any(keyword in lower for keyword in ["paint", "painter", "painting"]):
            return [
                f"residential painting companies {geography} free estimate",
                f"house painters {geography} request quote",
                f"interior exterior painting contractors {geography}",
            ]
        if " " in source and "." not in source:
            return [source]
        return [
            f"{target_customer} {geography}",
            f"{target_customer} request quote {geography}",
            f"{target_customer} business owner {geography}",
        ]
