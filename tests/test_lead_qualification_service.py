from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, LeadSeedInput
from db.session import create_database
from leads.repository import LeadRepository
from leads.schemas import AgentFitStatus, QualificationResult
from leads.service import LeadQualificationService
from products.repository import ProductRepository
from tests.test_discovery_candidates import product_input


class QualificationLLM:
    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model,
        context: dict | None = None,
    ):
        assert task == "lead_qualification"
        assert response_model is QualificationResult
        assert "Cedar & Sons Painting" in prompt
        return QualificationResult(
            qualified=True,
            score=83,
            rationale="Matches residential painting customer profile.",
            positive_signals=["Residential painting company"],
            missing_evidence=["Owner name not found"],
            risks=[],
            recommended_next_step="Draft outreach for human approval.",
        )


def test_single_lead_qualification_normalizes_and_persists_agent_fit() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(product_input())
        campaign = CampaignRepository(session).create(
            CampaignCreate(product_id=product.id, name="Painters Toronto", max_leads=5)
        )
        lead = LeadRepository(session).create_from_seed(
            campaign.id,
            product.id,
            LeadSeedInput(
                company_name="Cedar & Sons Painting",
                website_url="https://cedarpaint.example",
                contact_email="owner@cedarpaint.example",
                geography="Toronto, ON",
                description="Residential painting company",
            ),
        )

        updated = LeadQualificationService(session=session, llm=QualificationLLM()).qualify(lead.id)

        assert updated.qualification is not None
        assert updated.qualification.fit_status == AgentFitStatus.GOOD_FIT
        assert updated.qualification.score == 83
        assert updated.qualification.positive_signals == ["Residential painting company"]
        assert updated.qualification.missing_evidence == ["Owner name not found"]
