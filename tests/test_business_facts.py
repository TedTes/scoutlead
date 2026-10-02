from datetime import timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from business_facts.repository import BusinessFactKey, BusinessFactRepository, fact_value
from business_index.contracts import compile_search_contract
from business_index.schemas import BusinessIndexSearch, OpportunityType
from business_index.search import BusinessIndexSearchService
from canonical.repository import CanonicalRepository
from db.models import BusinessNicheMembershipModel, NicheModel, SourceObservationModel
from db.session import create_database
from shared.utils import new_id, utcnow


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _add_painting_niche(session) -> NicheModel:
    niche = NicheModel(
        id=new_id("niche"),
        slug="painting_contractors",
        label="Painting contractors",
        category="painting contractors",
        default_query="painting contractors",
        active=True,
        signal_vocabulary=[],
    )
    session.add(niche)
    session.commit()
    return niche


def _source_payload(
    status: str,
    *,
    external_id: str = "places/test-painter",
    phone: str = "416-555-0101",
) -> dict:
    return {
        "id": external_id,
        "businessStatus": "OPERATIONAL",
        "nationalPhoneNumber": phone,
        "website_presence": {"status": status},
        "source_request_intent": {
            "business_category": "painting contractors",
            "location": "Toronto",
            "search_query": "painting contractors in Toronto",
        },
    }


def test_repeated_provider_fetches_append_observations_and_preserve_identity() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        first = canonical.upsert_from_discovery_result(
            company_name="Test Painter",
            geography="Toronto",
            source="google_places",
            raw=_source_payload("no_website_listed"),
        )
        second = canonical.upsert_from_discovery_result(
            company_name="Test Painter",
            geography="Toronto",
            source="google_places",
            raw=_source_payload("no_website_listed"),
        )

        assert first.business_id == second.business_id
        assert first.source_observation_id != second.source_observation_id
        assert session.scalar(select(func.count()).select_from(SourceObservationModel)) == 2


def test_confirmed_evidence_reconciles_current_website_fact() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        link = canonical.upsert_from_discovery_result(
            company_name="Test Painter",
            geography="Toronto",
            source="google_places",
            raw=_source_payload("no_website_listed"),
        )
        facts = BusinessFactRepository(session).map_for_businesses([link.business_id])
        assert fact_value(facts[link.business_id][BusinessFactKey.WEBSITE_STATUS.value]) == "not_listed"

        canonical.record_business_evidence(
            business=session.get(SourceObservationModel, link.source_observation_id).business,
            source="website_presence_check",
            raw={"website_presence": {"status": "no_website_found"}},
        )
        facts = BusinessFactRepository(session).map_for_businesses([link.business_id])
        assert fact_value(facts[link.business_id][BusinessFactKey.WEBSITE_STATUS.value]) == "missing"

        canonical.upsert_from_discovery_result(
            company_name="Test Painter",
            website_url="https://testpainter.example",
            geography="Toronto",
            source="google_places",
            raw={**_source_payload("website_found_during_confirmation"), "websiteUri": "https://testpainter.example"},
        )
        facts = BusinessFactRepository(session).map_for_businesses([link.business_id])
        assert fact_value(facts[link.business_id][BusinessFactKey.WEBSITE_STATUS.value]) == "present"


def test_search_contract_matches_only_current_supported_facts() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        niche = _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        missing = canonical.upsert_from_discovery_result(
            company_name="Alpha Brushworks",
            geography="Toronto",
            source="google_places",
            raw=_source_payload("no_website_found", external_id="places/missing"),
        )
        canonical.upsert_from_discovery_result(
            company_name="Beta Coatings",
            website_url="https://website-painter.example",
            geography="Toronto",
            source="google_places",
            raw={
                **_source_payload(
                    "active",
                    external_id="places/present",
                    phone="416-555-0102",
                ),
                "websiteUri": "https://website-painter.example",
            },
        )
        contract = compile_search_contract(
            "Painters in Toronto without a website",
            opportunity_type=OpportunityType.MISSING_WEBSITE,
        )
        membership = session.scalar(
            select(BusinessNicheMembershipModel).where(
                BusinessNicheMembershipModel.business_id == missing.business_id
            )
        )
        assert membership is not None
        current_facts = BusinessFactRepository(session).map_for_businesses(
            [missing.business_id]
        )[missing.business_id]
        assert fact_value(current_facts[BusinessFactKey.WEBSITE_STATUS.value]) == "missing"

        rows, decisions = BusinessIndexSearchService(session).search_with_diagnostics(
            BusinessIndexSearch(
                niche_id=membership.niche_id,
                market_key="toronto",
                opportunity_type=OpportunityType.MISSING_WEBSITE,
                evidence_fresh_after=utcnow() - timedelta(days=30),
                result_count=10,
                contract=contract,
            )
        )

        assert [row["raw"]["canonical_business_id"] for row in rows] == [missing.business_id], decisions


def test_dynamic_contract_reports_unsupported_criteria() -> None:
    contract = compile_search_contract(
        (
            "Independent painters in Toronto with fewer than 12 reviews and no quote form. "
            "Exclude chains, franchises, directories, and web agencies."
        ),
        opportunity_type=OpportunityType.WEAK_OR_MISSING_WEBSITE,
    )

    assert {predicate.key for predicate in contract.any_of} == {
        BusinessFactKey.GOOGLE_REVIEW_COUNT.value,
        BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT.value,
    }
    assert set(contract.unsupported) == {
        "independent_or_chain_status",
        "directory_exclusion",
        "business_model_exclusion",
    }
