from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from types import SimpleNamespace
import pytest

from db.session import create_database
from products.routes import start_product_discovery
from products.schemas import (
    DiscoverySource,
    DiscoverySourceType,
    ProductCreate,
    ProductDescriptionCreate,
    ProductDiscoveryPlan,
    ProductDiscoveryStart,
    ProductSourceCreate,
    ProductSourceEvidence,
    QualificationCriterion,
)
from products.discovery_policy import (
    build_local_business_query,
    normalize_places_region_code,
    validate_local_business_intent,
    validate_google_places_query,
)
from products.service import ProductService
from shared.errors import ConfigurationError, ConflictError, ValidationError
from tools.browser import WebsiteInspection
from tools.search import SearchResult


class FakeBrowser:
    def __init__(self) -> None:
        self.calls = 0

    def inspect(self, url: str) -> WebsiteInspection:
        self.calls += 1
        return WebsiteInspection(
            url=url,
            title="QuoteVan",
            description="Fast quote intake for residential painting companies.",
            text="QuoteVan helps painters handle estimate requests and homeowner quote workflows.",
            links=["https://quotevan.com/features"],
        )


class SparseBrowser:
    def inspect(self, url: str) -> WebsiteInspection:
        return WebsiteInspection(url=url, title="QuoteVan", text="")


class SourceLookupSearch:
    is_configured = True

    def __init__(self) -> None:
        self.calls: list[str] = []

    def lookup(self, query: str, limit: int = 5) -> list[SearchResult]:
        self.calls.append(query)
        return [
            SearchResult(
                title="QuoteVan quote intake for residential painting contractors",
                url="https://quotevan.com",
                snippet=(
                    "QuoteVan helps residential painting companies manage homeowner quote "
                    "requests, estimate intake, and follow-up workflows from one simple form."
                ),
                source="test",
            )
        ]


class ExplodingBrowser:
    def inspect(self, url: str) -> WebsiteInspection:
        raise AssertionError("browser should not be used for description product creation")


class DescriptionConfigLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model,
        context: dict | None = None,
    ):
        self.calls.append(task)
        return ProductCreate(
            product_name=context["product_name"],
            product_description=(
                "QuoteVan lets solo painters price a job during the walkthrough and send "
                "a customer-ready quote before leaving the driveway."
            ),
            target_customer="Solo residential painters and small painting companies",
            problem_being_solved=(
                "Painters lose momentum when quotes are delayed, inconsistent, or rebuilt "
                "manually after a site visit."
            ),
            value_proposition=(
                "Turn walkthrough notes into a professional quote on the spot while keeping "
                "customer history organized."
            ),
            target_geography="Canada",
            validation_goal="Book customer discovery interviews with residential painters.",
            qualification_criteria=[
                QualificationCriterion(
                    label="Residential painting company",
                    weight=3,
                    required=True,
                    evidence_required=True,
                ),
                QualificationCriterion(
                    label="Publicly offers estimates or quote requests",
                    weight=2,
                    required=False,
                    evidence_required=True,
                ),
            ],
            preferred_discovery_sources=[
                DiscoverySource(
                    type=DiscoverySourceType.WEB_SEARCH,
                    value="residential painting companies United States request estimate",
                ),
                DiscoverySource(
                    type=DiscoverySourceType.WEB_SEARCH,
                    value="solo house painters United States free quote",
                ),
            ],
            outreach_objective="Ask for a short customer discovery conversation.",
            constraints=["Human approval required before outbound messages are sent."],
        )


class DiscoveryPlanLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.context = {}

    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model,
        context: dict | None = None,
    ):
        self.calls.append(task)
        self.context = context or {}
        assert response_model is ProductDiscoveryPlan
        return ProductDiscoveryPlan(
            product_name="Wrong Name",
            product_description="Wrong description that should be overwritten by the service.",
            target_customer="Owner-operated residential painting companies",
            problem_being_solved="Quotes are delayed or rebuilt manually after site visits.",
            value_proposition="Send professional quotes before leaving the job.",
            target_geography="Canada",
            validation_goal="Book customer discovery interviews with residential painters.",
            qualification_criteria=[
                QualificationCriterion(label="Offers residential painting", required=True),
                QualificationCriterion(label="Offers free estimates"),
                QualificationCriterion(label="Has phone or website"),
            ],
            discovery_query="residential painters Toronto ON",
            source_provider="google_places",
            region_code="CA",
            outreach_objective="Ask for a customer discovery conversation.",
            rationale="Local painters are discoverable through Google Places.",
        )


class BroadDiscoveryPlanLLM:
    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model,
        context: dict | None = None,
    ):
        assert response_model is ProductDiscoveryPlan
        return ProductDiscoveryPlan(
            product_name="QuoteVan",
            product_description="Quote workflow for solo painters.",
            target_customer="Solo painters",
            problem_being_solved="Quoting takes too long.",
            value_proposition="Send quotes faster.",
            target_geography="United States, Canada",
            validation_goal="Book customer discovery interviews.",
            qualification_criteria=[QualificationCriterion(label="Solo painter")],
            discovery_query=(
                "solo painter OR independent painter OR field service technician"
            ),
            outreach_objective="Ask for a customer discovery conversation.",
            rationale="This is intentionally too broad.",
        )


class SourceConfigLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model,
        context: dict | None = None,
    ):
        self.calls.append(task)
        if response_model is ProductSourceEvidence:
            lookup_snippets = [
                f"Source lookup result: {result['title']}"
                for result in (context or {}).get("source_lookup_results", [])
                if result.get("title")
            ]
            return ProductSourceEvidence(
                product_name_candidates=["QuoteVan"],
                headline="Fast quote intake for residential painting companies",
                claims=[
                    "QuoteVan helps painters handle estimate requests and homeowner quote workflows."
                ],
                target_customer_clues=["residential painting companies"],
                problem_clues=["estimate requests and homeowner quote workflows"],
                value_clues=["fast quote intake"],
                source_snippets=[
                    "Fast quote intake for residential painting companies.",
                    "QuoteVan helps painters handle estimate requests and homeowner quote workflows.",
                    *lookup_snippets,
                ],
                confidence=85,
                missing_info=[],
                rationale="The inspected source states the product, customer, and quote workflow.",
            )
        return ProductCreate(
            product_name="QuoteVan",
            product_description="Fast quote intake software for residential painting companies.",
            target_customer="Residential painting companies",
            problem_being_solved="Painters need a faster way to handle quote and estimate requests.",
            value_proposition="Help painters turn job details into customer-ready quotes faster.",
            target_geography="United States",
            validation_goal="Book customer discovery interviews with residential painting companies.",
            qualification_criteria=[
                QualificationCriterion(
                    label="Residential painting company",
                    weight=3,
                    required=True,
                    evidence_required=True,
                ),
                QualificationCriterion(
                    label="Offers estimates or quote requests",
                    weight=2,
                    evidence_required=True,
                ),
            ],
            preferred_discovery_sources=[
                DiscoverySource(
                    type=DiscoverySourceType.WEB_SEARCH,
                    value="residential painting companies United States request estimate",
                )
            ],
            outreach_objective="Ask for a short customer discovery conversation.",
            constraints=["Human approval required before outbound messages are sent."],
        )


class AmbiguousQuoteBrowser:
    def inspect(self, url: str) -> WebsiteInspection:
        return WebsiteInspection(
            url=url,
            title="QuoteVan",
            description="Compare quotes from local service providers.",
            text="QuoteVan helps customers request quotes and compare estimates from providers.",
        )


class CapturingLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.context = {}

    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model,
        context: dict | None = None,
    ):
        self.prompts.extend([system, prompt])
        self.context = context or {}
        if response_model is ProductSourceEvidence:
            return ProductSourceEvidence(
                product_name_candidates=["QuoteVan"],
                headline="Fast quote intake for residential painting companies",
                claims=["Fast quote intake for residential painting companies."],
                target_customer_clues=["residential painting companies"],
                problem_clues=["estimate requests"],
                value_clues=["fast quote intake"],
                source_snippets=["Fast quote intake for residential painting companies."],
                confidence=85,
                missing_info=[],
                rationale="Captured prompt test evidence.",
            )
        return SourceConfigLLM().generate_object(
            task=task,
            system=system,
            prompt=prompt,
            response_model=response_model,
            context=context,
        )


class VanRentalGuessLLM:
    def __init__(self) -> None:
        self.called = False

    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model,
        context: dict | None = None,
    ):
        self.called = True
        if response_model is ProductSourceEvidence:
            return ProductSourceEvidence(
                product_name_candidates=["QuoteVan"],
                headline="Compare quotes from local service providers",
                claims=["Compare quotes from local service providers."],
                target_customer_clues=["local service providers"],
                problem_clues=["customers request quotes and compare estimates"],
                value_clues=["compare estimates"],
                source_snippets=["Compare quotes from local service providers."],
                confidence=80,
                missing_info=[],
                rationale="Enough page evidence to draft, but not enough to infer van rentals.",
            )
        return ProductCreate(
            product_name="QuoteVan",
            product_description="A van rental comparison platform.",
            target_customer="People looking for van rentals and moving services",
            problem_being_solved="Customers need to compare van rental prices.",
            value_proposition="Compare transportation and delivery services.",
            target_geography="United States",
            validation_goal="Validate demand for van rentals.",
            qualification_criteria=[
                QualificationCriterion(label="Needs van rental", required=True),
            ],
            preferred_discovery_sources=[
                DiscoverySource(type=DiscoverySourceType.WEB_SEARCH, value="van rental companies"),
            ],
            outreach_objective="Ask for a discovery call.",
            constraints=["Human approval required before outbound messages are sent."],
        )


class InvalidProductConfigLLM:
    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model,
        context: dict | None = None,
    ):
        if response_model is ProductSourceEvidence:
            return ProductSourceEvidence(
                product_name_candidates=["QuoteVan"],
                headline="Quote the job before you leave it.",
                claims=["Walk the job, capture the scope, send a professional quote."],
                target_customer_clues=[],
                problem_clues=[],
                value_clues=["Send a professional quote."],
                source_snippets=["Quote the job before you leave it."],
                confidence=70,
                missing_info=["Specific target customer segments or industries"],
                rationale="Partial product evidence was found.",
            )
        return response_model.model_validate(
            {
                "product_name": "QuoteVan",
                "product_description": "Quote the job before you leave it.",
                "target_customer": "",
                "problem_being_solved": "Quote workflows are slow.",
                "value_proposition": "Send professional quotes faster.",
                "target_geography": "United States",
                "validation_goal": "Book customer discovery interviews.",
                "qualification_criteria": [{"label": "Matches target customer"}],
                "preferred_discovery_sources": [
                    {"type": "web_search", "value": "field service quote software"}
                ],
                "outreach_objective": "Ask for a customer discovery conversation.",
                "constraints": ["Human approval required before outbound messages are sent."],
            }
        )


class ChangingProductInferenceLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model,
        context: dict | None = None,
    ):
        self.calls.append(task)
        if response_model is ProductSourceEvidence:
            evidence_call_count = sum(call == "product_source_evidence" for call in self.calls)
            confidence = 80 if evidence_call_count == 1 else 82
            return ProductSourceEvidence(
                product_name_candidates=["QuoteVan"],
                headline="Quote the job before you leave it.",
                claims=["Walk the job, capture the scope, send a professional quote."],
                target_customer_clues=[],
                problem_clues=[],
                value_clues=["Send a professional quote."],
                source_snippets=[
                    "Walk the job, capture the scope, send a professional quote.",
                ],
                confidence=confidence,
                missing_info=[],
                rationale=f"Generated confidence {confidence}.",
            )
        draft_call_count = sum(call == "product_config_from_evidence" for call in self.calls)
        customer = "Residential painting companies" if draft_call_count == 1 else "Residential painting contractors"
        return ProductCreate(
            product_name="QuoteVan",
            product_description="Quote workflow software for residential painters.",
            target_customer=customer,
            problem_being_solved="Painting companies need faster estimate workflows.",
            value_proposition="Create customer-ready quotes from walkthrough details.",
            target_geography="United States",
            validation_goal="Book customer discovery interviews with residential painters.",
            qualification_criteria=[
                QualificationCriterion(label="Residential painting company", required=True),
            ],
            preferred_discovery_sources=[
                DiscoverySource(
                    type=DiscoverySourceType.WEB_SEARCH,
                    value="residential painting companies United States",
                )
            ],
            outreach_objective="Ask for a customer discovery conversation.",
            constraints=["Human approval required before outbound messages are sent."],
        )


def test_product_can_be_created_from_single_source() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductService(
            session,
            llm=SourceConfigLLM(),
            browser=FakeBrowser(),
        ).create_from_source(ProductSourceCreate(source="https://quotevan.com"))

        assert product.product_name == "QuoteVan"
        assert "painting" in product.target_customer.lower()
        assert product.qualification_criteria
        assert product.preferred_discovery_sources


def test_product_can_be_created_from_description_without_llm_or_scraping() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    llm = DescriptionConfigLLM()

    with session_factory() as session:
        product = ProductService(
            session,
            llm=llm,
            browser=ExplodingBrowser(),
        ).create_from_description(
            ProductDescriptionCreate(
                product_name="QuoteVan",
                description=(
                    "QuoteVan helps home-service painters capture job scope during a "
                    "walkthrough, send a professional quote before leaving the job, and "
                    "keep customer history in one place."
                )
            )
        )

        assert product.product_name == "QuoteVan"
        assert llm.calls == []
        assert product.target_customer == "Define target customer before running discovery."
        assert "walkthrough" in product.product_description.lower()
        assert product.target_geography == "United States, Canada"
        assert product.source_url is None
        assert product.source_fingerprint is None
        assert product.qualification_criteria
        assert product.preferred_discovery_sources == []
        assert product.source_evidence["config_generated_by"] == "deterministic_draft"


def test_product_discovery_plan_is_generated_from_saved_description() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    llm = DiscoveryPlanLLM()

    with session_factory() as session:
        service = ProductService(
            session,
            llm=llm,
            browser=ExplodingBrowser(),
        )
        product = service.create_from_description(
            ProductDescriptionCreate(
                product_name="QuoteVan",
                description=(
                    "QuoteVan helps home-service painters capture job scope during a "
                    "walkthrough, send a professional quote before leaving the job, and "
                    "keep customer history in one place. Start testing in Toronto, Canada."
                ),
            )
        )
        result = service.plan_discovery(product.id)
        updated = service.apply_discovery_plan(product.id, result)

        assert llm.calls == ["product_discovery_plan"]
        assert llm.context["product_name"] == "QuoteVan"
        assert result.product_name == "QuoteVan"
        assert result.product_description.startswith("QuoteVan helps")
        assert result.target_geography == "Canada"
        assert result.discovery_query == "residential painters Toronto ON"
        assert result.region_code == "CA"
        assert updated.target_customer == "Owner-operated residential painting companies"
        assert updated.preferred_discovery_sources[0]["value"] == "residential painters Toronto ON"
        assert updated.source_evidence["source_provider"] == "google_places"
        assert updated.source_evidence["source_provider_selected_by"] == "application_policy"


def test_product_discovery_query_policy_rejects_broad_web_search_syntax() -> None:
    with pytest.raises(ValidationError):
        validate_google_places_query(
            "solo painter OR independent painter OR field service technician"
        )
    with pytest.raises(ValidationError):
        validate_google_places_query("residential painters Toronto ON site:example.com")


def test_product_discovery_query_policy_allows_natural_language_and() -> None:
    validate_google_places_query(
        "residential painting contractors Toronto ON with direct phone contact and quote-ready service pages"
    )


def test_local_business_intent_uses_parsed_location_dynamically() -> None:
    assert (
        build_local_business_query(
            business_category="residential painting contractors",
            location="Toronto",
            fallback_query="residential painting contractors Toronto with direct phone contact",
        )
        == "residential painting contractors Toronto"
    )


def test_local_business_intent_requires_parsed_market_context() -> None:
    with pytest.raises(ValidationError):
        validate_local_business_intent(
            business_category="residential painters",
            location="",
            query="residential painters",
        )


def test_product_discovery_query_policy_requires_enough_query_context() -> None:
    with pytest.raises(ValidationError):
        validate_google_places_query("residential painters")

    validate_google_places_query("residential painters Toronto ON")
    assert normalize_places_region_code("Canada") == "CA"


def test_product_discovery_rejects_broad_plan_before_persisting_profile() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        service = ProductService(session, llm=None, browser=ExplodingBrowser())
        product = service.create_from_description(
            ProductDescriptionCreate(
                product_name="QuoteVan",
                description=(
                    "QuoteVan helps solo painters send professional quotes faster. "
                    "The operator has not provided a concrete test market."
                ),
            )
        )

        with pytest.raises(ValidationError):
            start_product_discovery(
                product.id,
                ProductDiscoveryStart(max_results=10),
                session,
                SimpleNamespace(llm=BroadDiscoveryPlanLLM(), browser=None, search=None),
            )

        unchanged = service.get(product.id)
        assert unchanged.preferred_discovery_sources == []
        assert unchanged.source_evidence["config_generated_by"] == "deterministic_draft"


def test_product_description_creation_succeeds_without_llm() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductService(
            session,
            llm=None,
            browser=ExplodingBrowser(),
        ).create_from_description(
            ProductDescriptionCreate(
                product_name="QuoteVan",
                description=(
                    "QuoteVan helps home-service painters capture job scope during a "
                    "walkthrough, send a professional quote before leaving the job, and "
                    "keep customer history in one place."
                )
            )
        )

        assert product.product_name == "QuoteVan"
        assert product.target_geography == "United States, Canada"


def test_duplicate_product_name_is_rejected() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        service = ProductService(
            session,
            llm=None,
            browser=ExplodingBrowser(),
        )
        request = ProductDescriptionCreate(
            product_name="QuoteVan",
            description=(
                "QuoteVan helps home-service painters capture job scope during a "
                "walkthrough, send a professional quote before leaving the job, and "
                "keep customer history in one place."
            ),
        )

        service.create_from_description(request)

        with pytest.raises(ConflictError):
            service.create_from_description(
                ProductDescriptionCreate(
                    product_name=" quotevan ",
                    description=(
                        "A second description for the same product name should not create "
                        "another active product record."
                    ),
                )
            )


def test_same_source_reuses_existing_product_without_refetching() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    browser = FakeBrowser()

    with session_factory() as session:
        service = ProductService(
            session,
            llm=SourceConfigLLM(),
            browser=browser,
        )
        product = service.create_from_source(ProductSourceCreate(source="https://quotevan.com"))
        calls_after_create = browser.calls

        inference = service.infer_product_from_source(
            ProductSourceCreate(source="https://www.quotevan.com/")
        )
        recreated = service.create_from_source(ProductSourceCreate(source="quotevan.com/"))

        assert browser.calls == calls_after_create
        assert inference.existing_product is not None
        assert inference.existing_product.id == product.id
        assert inference.product.product_description == product.product_description
        assert recreated.id == product.id
        assert session.execute(text("select count(*) from products")).scalar_one() == 1


def test_same_source_reuses_legacy_product_name_match_without_refetching() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    browser = FakeBrowser()

    with session_factory() as session:
        product = ProductService(session).create(
            ProductCreate(
                product_name="QuoteVan",
                product_description="Saved before source metadata existed.",
                target_customer="Residential painting companies",
                problem_being_solved="Quote requests are slow.",
                value_proposition="Organize quote intake.",
                target_geography="United States",
                validation_goal="Book customer discovery interviews.",
                qualification_criteria=[
                    QualificationCriterion(label="Matches target customer", required=True),
                ],
                preferred_discovery_sources=[
                    DiscoverySource(
                        type=DiscoverySourceType.WEB_SEARCH,
                        value="residential painting companies United States",
                    )
                ],
                outreach_objective="Ask for a customer discovery conversation.",
                constraints=["Human approval required before outbound messages are sent."],
            )
        )

        inference = ProductService(
            session,
            llm=None,
            browser=browser,
        ).infer_product_from_source(ProductSourceCreate(source="https://www.quotevan.com/"))

        session.refresh(product)
        assert browser.calls == 0
        assert inference.existing_product is not None
        assert inference.existing_product.id == product.id
        assert product.source_url == "https://quotevan.com"
        assert product.source_fingerprint


def test_product_source_prompt_does_not_treat_scoutlead_as_product() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    llm = CapturingLLM()

    with session_factory() as session:
        ProductService(
            session,
            llm=llm,
            browser=FakeBrowser(),
        ).infer_from_source(ProductSourceCreate(source="https://quotevan.com"))

        joined_prompts = "\n".join(llm.prompts)
        assert "ScoutLead" not in joined_prompts
        assert "submitted source" in joined_prompts
        assert llm.context["source"] == "https://quotevan.com"


def test_sparse_source_fails_without_generating_product_guess() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    llm = VanRentalGuessLLM()

    with session_factory() as session:
        with pytest.raises(ValidationError):
            ProductService(
                session,
                llm=llm,
                browser=SparseBrowser(),
            ).infer_product_from_source(ProductSourceCreate(source="https://quotevan.com"))

        assert llm.called is False


def test_sparse_source_uses_source_lookup_before_needing_context() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    search = SourceLookupSearch()

    with session_factory() as session:
        inference = ProductService(
            session,
            llm=SourceConfigLLM(),
            browser=SparseBrowser(),
            search=search,
        ).infer_product_from_source(ProductSourceCreate(source="https://quotevan.com"))

        assert search.calls
        assert inference.ready_to_save is True
        assert "painting" in inference.product.target_customer.lower()
        assert "quote" in inference.product.problem_being_solved.lower()
        assert any("Source lookup result" in snippet for snippet in inference.evidence.source_snippets)


def test_repeated_source_inference_uses_cached_draft() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    llm = ChangingProductInferenceLLM()
    browser = FakeBrowser()

    with session_factory() as session:
        service = ProductService(
            session,
            llm=llm,
            browser=browser,
        )
        first = service.infer_product_from_source(ProductSourceCreate(source="https://quotevan.com"))
        browser_calls = browser.calls
        second = service.infer_product_from_source(ProductSourceCreate(source="https://www.quotevan.com/"))

        assert first.confidence == 80
        assert second.confidence == first.confidence
        assert browser.calls == browser_calls
        assert llm.calls == ["product_source_evidence", "product_config_from_evidence"]


def test_context_change_triggers_new_llm_inference() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    llm = ChangingProductInferenceLLM()

    with session_factory() as session:
        service = ProductService(
            session,
            llm=llm,
            browser=FakeBrowser(),
        )
        base = service.infer_product_from_source(ProductSourceCreate(source="https://quotevan.com"))
        refined = service.infer_product_from_source(
            ProductSourceCreate(
                source="https://quotevan.com",
                context="Quote intake workflow for residential painting companies",
            )
        )

        assert refined.confidence >= base.confidence
        assert refined.ready_to_save is True
        assert "painting" in refined.product.target_customer.lower()
        assert llm.calls == [
            "product_source_evidence",
            "product_config_from_evidence",
            "product_source_evidence",
            "product_config_from_evidence",
        ]


def test_invalid_llm_product_config_raises_without_substitute_data() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        with pytest.raises(Exception):
            ProductService(
                session,
                llm=InvalidProductConfigLLM(),
                browser=FakeBrowser(),
            ).infer_product_from_source(ProductSourceCreate(source="https://quotevan.com"))


def test_ungrounded_van_rental_inference_is_rejected() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    llm = VanRentalGuessLLM()

    with session_factory() as session:
        with pytest.raises(ValidationError):
            ProductService(
                session,
                llm=llm,
                browser=AmbiguousQuoteBrowser(),
            ).infer_from_source(ProductSourceCreate(source="https://quotevan.com"))

        assert llm.called is True


def test_sparse_source_with_user_context_can_generate_saveable_draft() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        inference = ProductService(
            session,
            llm=SourceConfigLLM(),
            browser=SparseBrowser(),
        ).infer_product_from_source(
            ProductSourceCreate(
                source="https://quotevan.com",
                context="Quote intake workflow for residential painting companies",
            )
        )

        assert inference.ready_to_save is True
        assert "painting" in inference.product.target_customer.lower()
