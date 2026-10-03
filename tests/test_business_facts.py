from datetime import timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from business_facts.repository import BusinessFactKey, BusinessFactRepository, fact_value
from business_index.contracts import compile_search_contract, search_contract_hash
from business_index.schemas import BusinessIndexSearch, OpportunityType
from business_index.search import BusinessIndexSearchService
from canonical.repository import CanonicalRepository
from db.models import BusinessNicheMembershipModel, NicheModel, SourceObservationModel
from db.session import create_database
from shared.utils import new_id, utcnow
from search_evaluations.schemas import (
    SearchCriterionEvaluation,
    SearchEvaluationResult,
    SearchEvaluationStatus,
)
from search_evaluations.service import SearchEvaluationService
from source_requests.schemas import (
    SearchCriterionMode,
    SearchIntentCriterion,
    SourceRequestIntent,
)


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
            _intent(
                SearchIntentCriterion(
                    id="missing_website",
                    description="Website is missing",
                    mode=SearchCriterionMode.REQUIRED,
                    fact_key="website_status",
                    operator="equals",
                    value="missing",
                )
            )
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
        _intent(
            SearchIntentCriterion(
                id="few_reviews",
                description="Fewer than 12 reviews",
                mode=SearchCriterionMode.ALTERNATIVE,
                fact_key="google_review_count",
                operator="less_than",
                value=12,
            ),
            SearchIntentCriterion(
                id="no_quote_form",
                description="No quote form",
                mode=SearchCriterionMode.ALTERNATIVE,
                fact_key="quote_or_booking_form_present",
                operator="equals",
                value=False,
            ),
            SearchIntentCriterion(
                id="independent",
                description="Independent business",
                mode=SearchCriterionMode.REQUIRED,
            ),
            SearchIntentCriterion(
                id="exclude_chains",
                description="National chains and franchises",
                mode=SearchCriterionMode.EXCLUDED,
            ),
        )
    )

    assert {predicate.key for predicate in contract.any_of} == {
        BusinessFactKey.GOOGLE_REVIEW_COUNT.value,
        BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT.value,
    }
    assert contract.semantic_all_of == ("Independent business",)
    assert contract.semantic_exclusions == ("National chains and franchises",)
    assert contract.unsupported == ()


def test_semantic_search_evaluation_is_reused_until_business_evidence_changes() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        niche = _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        business = canonical.upsert_from_discovery_result(
            company_name="Alpha Brushworks",
            geography="Toronto",
            description="Independent residential painting contractor",
            source="google_places",
            raw=_source_payload("no_website_found", external_id="places/alpha"),
        )
        intent = _intent(
            SearchIntentCriterion(
                id="independent",
                description="Independent owner-operated business",
                mode=SearchCriterionMode.REQUIRED,
            )
        )
        contract = compile_search_contract(intent)
        contract_hash = search_contract_hash(intent, contract)
        request = BusinessIndexSearch(
            niche_id=niche.id,
            market_key="toronto",
            opportunity_type=OpportunityType.ANY,
            evidence_fresh_after=utcnow() - timedelta(days=30),
            result_count=10,
            contract=contract,
            contract_hash=contract_hash,
        )

        rows, decisions = BusinessIndexSearchService(session).search_with_diagnostics(request)
        assert rows == []
        assert [decision["status"] for decision in decisions] == ["pending"]

        llm = MatchingEvaluationLLM()
        SearchEvaluationService(session=session, llm=llm).evaluate(
            business_id=business.business_id,
            contract_hash=contract_hash,
            contract=contract,
        )
        rows = BusinessIndexSearchService(session).search(request)
        assert [row["raw"]["canonical_business_id"] for row in rows] == [business.business_id]
        assert llm.calls == 1

        canonical.upsert_from_discovery_result(
            company_name="Alpha Brushworks",
            geography="Toronto",
            description="Updated public listing",
            source="google_places",
            raw=_source_payload("no_website_found", external_id="places/alpha"),
        )
        rows, decisions = BusinessIndexSearchService(session).search_with_diagnostics(request)
        assert rows == []
        assert [decision["status"] for decision in decisions] == ["pending"]


def test_explicit_present_website_contract_does_not_use_opportunity_fallback() -> None:
    contract = compile_search_contract(
        _intent(
            SearchIntentCriterion(
                id="website_present",
                description="Business has a website",
                mode=SearchCriterionMode.REQUIRED,
                fact_key="website_status",
                operator="equals",
                value="present",
            )
        )
    )

    assert [(predicate.key, predicate.value) for predicate in contract.all_of] == [
        (BusinessFactKey.WEBSITE_STATUS.value, "present")
    ]
    assert contract.any_of == ()


def test_explicit_present_website_contract_returns_current_present_website() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        niche = _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        canonical.upsert_from_discovery_result(
            company_name="Alpha Brushworks",
            geography="Toronto",
            source="google_places",
            raw=_source_payload("no_website_found", external_id="places/missing"),
        )
        present = canonical.upsert_from_discovery_result(
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
            _intent(
                SearchIntentCriterion(
                    id="website_present",
                    description="Business has a website",
                    mode=SearchCriterionMode.REQUIRED,
                    fact_key="website_status",
                    operator="equals",
                    value="present",
                )
            )
        )

        rows = BusinessIndexSearchService(session).search(
            BusinessIndexSearch(
                niche_id=niche.id,
                market_key="toronto",
                opportunity_type=OpportunityType.ANY,
                evidence_fresh_after=utcnow() - timedelta(days=30),
                result_count=10,
                contract=contract,
            )
        )

        assert [row["raw"]["canonical_business_id"] for row in rows] == [
            present.business_id
        ]


def _intent(*criteria: SearchIntentCriterion) -> SourceRequestIntent:
    return SourceRequestIntent(
        business_category="painting contractors",
        location="Toronto",
        criteria=list(criteria),
        search_query="painting contractors in Toronto",
        confidence=100,
        rationale="Test intent",
    )


class MatchingEvaluationLLM:
    def __init__(self) -> None:
        self.calls = 0

    def generate_object(self, **kwargs):
        self.calls += 1
        assert kwargs["response_model"] is SearchEvaluationResult
        return SearchEvaluationResult(
            status=SearchEvaluationStatus.MATCHED,
            confidence=92,
            rationale="Current public evidence supports the criterion.",
            criteria=[
                SearchCriterionEvaluation(
                    criterion="Independent owner-operated business",
                    matched=True,
                    evidence=["Independent residential painting contractor"],
                )
            ],
            evidence=["Independent residential painting contractor"],
        )
