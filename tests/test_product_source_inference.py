from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from agents.llm import HeuristicLLMClient
from db.session import create_database
from products.schemas import (
    DiscoverySource,
    DiscoverySourceType,
    ProductCreate,
    ProductSourceCreate,
    ProductSourceEvidence,
    QualificationCriterion,
)
from products.service import ProductService
from tools.browser import WebsiteInspection


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
        assert "rental" not in inference.product.target_customer.lower()
        assert "moving" not in inference.product.target_customer.lower()


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
