from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from agents.llm import HeuristicLLMClient
from db.session import create_database
from products.schemas import (
    DiscoverySource,
    DiscoverySourceType,
    ProductCreate,
    ProductDescriptionCreate,
    ProductSourceCreate,
    ProductSourceEvidence,
    QualificationCriterion,
)
from products.service import ProductService
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


class ExplodingLLM:
    def generate_object(self, **kwargs):
        raise AssertionError("llm should not be used for description product creation")


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
        fallback,
    ):
        self.prompts.extend([system, prompt])
        self.context = context or {}
        return fallback


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
        fallback,
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
        fallback,
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
        fallback,
    ):
        self.calls.append(task)
        if response_model is ProductSourceEvidence:
            evidence_call_count = sum(call == "product_source_evidence" for call in self.calls)
            confidence = 80 if evidence_call_count == 1 else 10
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
                missing_info=["Specific target customer segments or industries served"],
                rationale=f"Generated confidence {confidence}.",
            )
        return fallback


def test_product_can_be_created_from_single_source() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductService(
            session,
            llm=HeuristicLLMClient(),
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

    with session_factory() as session:
        product = ProductService(
            session,
            llm=ExplodingLLM(),
            browser=ExplodingBrowser(),
        ).create_from_description(
            ProductDescriptionCreate(
                description=(
                    "QuoteVan helps home-service painters capture job scope during a "
                    "walkthrough, send a professional quote before leaving the job, and "
                    "keep customer history in one place."
                )
            )
        )

        assert product.product_name == "QuoteVan"
        assert "painters" in product.target_customer.lower()
        assert "quote" in product.problem_being_solved.lower()
        assert product.source_url is None
        assert product.source_fingerprint is None
        assert product.qualification_criteria
        assert product.preferred_discovery_sources


def test_same_source_reuses_existing_product_without_refetching() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    browser = FakeBrowser()

    with session_factory() as session:
        service = ProductService(
            session,
            llm=HeuristicLLMClient(),
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
            llm=HeuristicLLMClient(),
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


def test_sparse_source_uses_fallback_without_llm_guessing() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    llm = VanRentalGuessLLM()

    with session_factory() as session:
        inference = ProductService(
            session,
            llm=llm,
            browser=SparseBrowser(),
        ).infer_product_from_source(ProductSourceCreate(source="https://quotevan.com"))

        assert llm.called is False
        assert inference.ready_to_save is False
        assert "unknown" in inference.product.target_customer.lower()
        assert "not enough public source evidence" in inference.product.problem_being_solved.lower()
        assert "rental" not in inference.product.target_customer.lower()
        assert "moving" not in inference.product.target_customer.lower()


def test_sparse_source_uses_source_lookup_before_needing_context() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    search = SourceLookupSearch()

    with session_factory() as session:
        inference = ProductService(
            session,
            llm=HeuristicLLMClient(),
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


def test_context_refines_cached_source_draft_without_lowering_confidence() -> None:
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
        assert llm.calls == ["product_source_evidence", "product_config_from_evidence"]


def test_invalid_llm_product_config_falls_back_without_crashing() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        inference = ProductService(
            session,
            llm=InvalidProductConfigLLM(),
            browser=FakeBrowser(),
        ).infer_product_from_source(ProductSourceCreate(source="https://quotevan.com"))

        assert inference.ready_to_save is False
        assert inference.product.target_customer
        assert inference.product.target_customer != ""


def test_ungrounded_van_rental_inference_is_rejected() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    llm = VanRentalGuessLLM()

    with session_factory() as session:
        product = ProductService(
            session,
            llm=llm,
            browser=AmbiguousQuoteBrowser(),
        ).infer_from_source(ProductSourceCreate(source="https://quotevan.com"))

        assert llm.called is True
        generated = " ".join(
            [
                product.target_customer,
                product.problem_being_solved,
                product.value_proposition,
            ]
        ).lower()
        assert "van rental" not in generated
        assert "moving services" not in generated


def test_sparse_source_with_user_context_can_generate_saveable_draft() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        inference = ProductService(
            session,
            llm=HeuristicLLMClient(),
            browser=SparseBrowser(),
        ).infer_product_from_source(
            ProductSourceCreate(
                source="https://quotevan.com",
                context="Quote intake workflow for residential painting companies",
            )
        )

        assert inference.ready_to_save is True
        assert "painting" in inference.product.target_customer.lower()
