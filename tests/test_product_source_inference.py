from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.llm import HeuristicLLMClient
from db.session import create_database
from products.schemas import ProductCreate, ProductSourceCreate
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
