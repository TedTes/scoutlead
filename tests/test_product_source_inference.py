from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.llm import HeuristicLLMClient
from db.session import create_database
from products.schemas import (
    DiscoverySource,
    DiscoverySourceType,
    ProductCreate,
    ProductSourceCreate,
    QualificationCriterion,
)
from products.service import ProductService
from tools.browser import WebsiteInspection


class FakeBrowser:
    def inspect(self, url: str) -> WebsiteInspection:
        return WebsiteInspection(
            url=url,
            title="QuoteVan",
            description="Fast quote intake for residential painting companies.",
            text="QuoteVan helps painters handle estimate requests and homeowner quote workflows.",
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
        self.prompt = ""
        self.context = {}

    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model: type[ProductCreate],
        context: dict | None = None,
        fallback: ProductCreate,
    ) -> ProductCreate:
        self.prompt = prompt
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
        response_model: type[ProductCreate],
        context: dict | None = None,
        fallback: ProductCreate,
    ) -> ProductCreate:
        self.called = True
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

        assert "for ScoutLead" not in llm.prompt
        assert "submitted source" in llm.prompt
        assert llm.context["source"] == "https://quotevan.com"


def test_sparse_source_uses_fallback_without_llm_guessing() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    llm = VanRentalGuessLLM()

    with session_factory() as session:
        product = ProductService(
            session,
            llm=llm,
            browser=SparseBrowser(),
        ).infer_from_source(ProductSourceCreate(source="https://quotevan.com"))

        assert llm.called is False
        assert "rental" not in product.target_customer.lower()
        assert "moving" not in product.target_customer.lower()


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
