from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, LeadSeedInput
from db.models import BusinessModel, ContactModel, NicheModel, OutcomeModel
from db.session import create_database
from leads.repository import LeadRepository
from outcomes.policy import is_positive_outcome, no_response_due
from outcomes.schemas import (
    LeadOutcome,
    LeadOutcomeCreate,
    OutcomeChannel,
    OutcomeSource,
)
from outcomes.service import OutcomeService
from outcomes.maintenance import run_outcome_maintenance
from products.repository import ProductRepository
from products.schemas import ProductCreate, QualificationCriterion
from shared.errors import NotFoundError
from shared.utils import new_id, utcnow
from territories.schemas import TerritoryCreate
from territories.service import TerritoryService


def test_outcome_records_territory_dimensions_and_latest_value() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        lead, territory = _territory_lead(session, workspace_id="workspace:first")
        service = OutcomeService(
            session,
            workspace_id="workspace:first",
            recorded_by="user:first",
        )

        outcome = service.record(
            lead.id,
            LeadOutcomeCreate(
                outcome=LeadOutcome.REPLIED_POSITIVE,
                channel=OutcomeChannel.EMAIL,
                note="Interested in a meeting.",
            ),
        )

        session.refresh(lead)
        assert outcome.territory_id == territory.id
        assert outcome.niche_id == territory.niche_id
        assert outcome.market_key == "toronto"
        assert outcome.recorded_by == "user:first"
        assert lead.latest_outcome == LeadOutcome.REPLIED_POSITIVE.value
        assert is_positive_outcome(lead.latest_outcome) is True


def test_backdated_outcome_does_not_replace_newer_latest_outcome() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        lead, _ = _territory_lead(session, workspace_id="workspace:first")
        service = OutcomeService(session, workspace_id="workspace:first")
        now = utcnow()
        service.record(
            lead.id,
            LeadOutcomeCreate(outcome=LeadOutcome.WON, occurred_at=now),
        )
        service.record(
            lead.id,
            LeadOutcomeCreate(
                outcome=LeadOutcome.CONTACTED,
                occurred_at=now - timedelta(days=2),
            ),
        )

        session.refresh(lead)
        assert lead.latest_outcome == LeadOutcome.WON.value
        assert len(service.list_for_lead(lead.id)) == 2


def test_data_quality_outcomes_update_canonical_data_but_not_fit_outcomes() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        lead, _ = _territory_lead(session, workspace_id="workspace:first")
        service = OutcomeService(session, workspace_id="workspace:first")
        contact = session.get(ContactModel, lead.contact_id)
        business = session.get(BusinessModel, lead.business_id)

        service.record(lead.id, LeadOutcomeCreate(outcome=LeadOutcome.NOT_A_FIT))
        assert contact.verification_status == "unverified"
        assert business.status == "active"

        service.record(lead.id, LeadOutcomeCreate(outcome=LeadOutcome.WRONG_CONTACT))
        session.refresh(contact)
        assert contact.verification_status == "invalid"

        service.record(lead.id, LeadOutcomeCreate(outcome=LeadOutcome.BUSINESS_CLOSED))
        session.refresh(business)
        assert business.status == "closed"


def test_outcomes_are_workspace_scoped() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        lead, _ = _territory_lead(session, workspace_id="workspace:first")
        OutcomeService(session, workspace_id="workspace:first").record(
            lead.id,
            LeadOutcomeCreate(outcome=LeadOutcome.CONTACTED),
        )

        with pytest.raises(NotFoundError):
            OutcomeService(session, workspace_id="workspace:other").list_for_lead(lead.id)


def test_due_no_response_is_added_only_after_window() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        lead, _ = _territory_lead(session, workspace_id="workspace:first")
        service = OutcomeService(session, workspace_id="workspace:first")
        now = utcnow()
        contacted_at = now - timedelta(days=15)
        service.record(
            lead.id,
            LeadOutcomeCreate(
                outcome=LeadOutcome.CONTACTED,
                channel=OutcomeChannel.EMAIL,
                source=OutcomeSource.EMAIL_SEND,
                occurred_at=contacted_at,
            ),
        )

        assert no_response_due(
            contacted_at=contacted_at,
            latest_outcome=LeadOutcome.CONTACTED,
            now=now,
            days=14,
        )
        assert service.record_due_no_responses(days=14, now=now) == 1
        session.refresh(lead)
        assert lead.latest_outcome == LeadOutcome.NO_RESPONSE.value
        assert service.record_due_no_responses(days=14, now=now) == 0


def test_learning_model_recomputes_after_ten_new_outcomes() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        lead, territory = _territory_lead(session, workspace_id="workspace:first")
        service = OutcomeService(session, workspace_id="workspace:first")

        for index in range(10):
            service.record(
                lead.id,
                LeadOutcomeCreate(
                    outcome=(
                        LeadOutcome.CONTACTED
                        if index == 0
                        else LeadOutcome.NO_RESPONSE
                    ),
                    occurred_at=utcnow() + timedelta(seconds=index),
                ),
            )

        model = session.query(OutcomeModel).one()
        assert model.n_contacted == 1
        assert model.n_positive == 0
        assert model.niche_id == territory.niche_id


def test_daily_maintenance_records_due_no_response() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        lead, territory = _territory_lead(session, workspace_id="workspace:first")
        OutcomeService(session, workspace_id="workspace:first").record(
            lead.id,
            LeadOutcomeCreate(
                outcome=LeadOutcome.CONTACTED,
                occurred_at=utcnow() - timedelta(days=15),
            ),
        )

        run_outcome_maintenance(session, no_response_days=14)

        session.refresh(lead)
        assert lead.latest_outcome == LeadOutcome.NO_RESPONSE.value
        assert session.query(OutcomeModel).one().niche_id == territory.niche_id


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _territory_lead(session, *, workspace_id: str):
    product = ProductRepository(session, workspace_id=workspace_id).create(
        ProductCreate(
            product_name="Contractor Coverage",
            offer_summary="Commercial insurance for contractors.",
            target_customer="HVAC contractors",
            target_geography="Toronto",
            qualification_criteria=[QualificationCriterion(label="HVAC business")],
        )
    )
    niche = NicheModel(
        id=new_id("niche"),
        slug="home_service_hvac",
        label="HVAC contractors",
        category="HVAC",
        default_query="HVAC contractors",
        active=True,
    )
    session.add(niche)
    session.commit()
    territory = TerritoryService(session, workspace_id=workspace_id).create(
        TerritoryCreate(
            product_id=product.id,
            niche_id=niche.id,
            niche_slug=niche.slug,
            niche_label=niche.label,
            market_key="Toronto",
            confirmed=True,
        )
    )
    campaign = CampaignRepository(session, workspace_id=workspace_id).create(
        CampaignCreate(
            product_id=product.id,
            territory_id=territory.id,
            name="HVAC Toronto",
            max_leads=25,
        )
    )
    lead = LeadRepository(session, workspace_id=workspace_id).create_from_seed(
        campaign.id,
        product.id,
        LeadSeedInput(
            company_name="Example HVAC",
            website_url="https://example-hvac.test",
            contact_email="owner@example-hvac.test",
            geography="Toronto",
            description="Independent HVAC contractor",
        ),
    )
    return lead, territory
