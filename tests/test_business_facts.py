from datetime import timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from business_attributes.repository import BusinessAttributeKey, BusinessAttributeRepository, attribute_value
from business_attributes.repository import BusinessAttributeValue
from business_attributes.source_payloads import source_payload_attribute_key
from business_attributes.service import _replace_website_fact
from business_index.contracts import compile_search_contract
from business_index.schemas import BusinessIndexSearch, OpportunityType
from business_index.search import BusinessIndexSearchService
from canonical.repository import CanonicalRepository
from db.models import (
    BusinessModel,
    BusinessAttributeModel,
    BusinessNicheMembershipModel,
    NicheModel,
    SignalDefinitionModel,
)
from db.session import create_database
from shared.utils import new_id, utcnow
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


def test_repeated_provider_fetches_reuse_unchanged_observation_and_preserve_identity() -> None:
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
        assert first.source_evidence_id == second.source_evidence_id
        assert session.scalar(
            select(func.count()).select_from(BusinessAttributeModel).where(
                BusinessAttributeModel.business_id == first.business_id,
                BusinessAttributeModel.attribute_key
                == source_payload_attribute_key("google_places"),
            )
        ) == 1

        changed = canonical.upsert_from_discovery_result(
            company_name="Test Painter",
            geography="Toronto",
            source="google_places",
            raw={**_source_payload("no_website_listed"), "rating": 4.8},
        )

        assert changed.source_evidence_id == first.source_evidence_id
        changed_attribute = session.get(
            BusinessAttributeModel, changed.source_evidence_id
        )
        assert changed_attribute is not None
        assert changed_attribute.evidence["rating"] == 4.8
        assert session.scalar(
            select(func.count()).select_from(BusinessAttributeModel).where(
                BusinessAttributeModel.business_id == first.business_id,
                BusinessAttributeModel.attribute_key
                == source_payload_attribute_key("google_places"),
            )
        ) == 1


def test_canonical_business_attributes_are_materialized_and_scored() -> None:
    factory = _session_factory()
    with factory() as session:
        _add_painting_niche(session)
        session.add_all(
            [
                SignalDefinitionModel(
                    id=f"attribute_{key}",
                    key=key,
                    label=key.replace("_", " ").title(),
                    value_type=value_type,
                    category="identity",
                    status="derived",
                    freshness_days=365,
                    opportunity_direction=(
                        "false_is_opportunity"
                        if key == "google_business_profile_present"
                        else "none"
                    ),
                    config={},
                    version=1,
                )
                for key, value_type in (
                    ("business_name", "text"),
                    ("provider_business_id", "text"),
                    ("city", "text"),
                    ("region", "text"),
                    ("postal_code", "text"),
                    ("google_business_profile_present", "boolean"),
                )
            ]
        )
        session.commit()
        link = CanonicalRepository(session).upsert_from_discovery_result(
            company_name="Scored Painting Co.",
            website_url="https://scoredpainting.example",
            geography="Toronto, ON",
            source="google_places",
            raw={
                **_source_payload("present", external_id="places/scored-painting"),
                "city": "Toronto",
                "province": "Ontario",
                "postal_code": "M5V 1A1",
                "latitude": 43.65,
                "longitude": -79.38,
            },
        )

        facts = BusinessAttributeRepository(session).map_for_businesses(
            [link.business_id]
        )[link.business_id]

        assert attribute_value(facts["business_name"]) == "Scored Painting Co."
        assert attribute_value(facts["provider_business_id"]) == "places/scored-painting"
        assert attribute_value(facts["city"]) == "Toronto"
        assert attribute_value(facts["region"]) == "Ontario"
        assert attribute_value(facts["postal_code"]) == "M5V 1A1"
        assert attribute_value(facts["google_business_profile_present"]) is True
        assert facts["business_name"].attribute_score == 0
        assert facts["google_business_profile_present"].attribute_score == 0
        assert facts["business_name"].confidence == 95


def test_google_reputation_facts_require_google_places_provenance() -> None:
    factory = _session_factory()
    with factory() as session:
        _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        website_seed = canonical.upsert_from_discovery_result(
            company_name="Reputation Source Painter",
            geography="Toronto",
            source="company_website_seed",
            raw={
                "external_id": "website-seed/reputation-painter",
                "rating": 2.0,
                "review_count": 3,
            },
        )

        facts = BusinessAttributeRepository(session).map_for_businesses(
            [website_seed.business_id]
        ).get(website_seed.business_id, {})
        assert "google_rating" not in facts
        assert "google_review_count" not in facts

        canonical.upsert_from_discovery_result(
            company_name="Reputation Source Painter",
            geography="Toronto",
            source="google_places",
            raw={
                "id": "places/reputation-painter",
                "rating": 4.7,
                "userRatingCount": 28,
            },
        )

        facts = BusinessAttributeRepository(session).map_for_businesses(
            [website_seed.business_id]
        )[website_seed.business_id]
        assert attribute_value(facts["google_rating"]) == 4.7
        assert attribute_value(facts["google_review_count"]) == 28.0


def test_reconciliation_does_not_materialize_unknown_placeholder_facts() -> None:
    factory = _session_factory()
    with factory() as session:
        _add_painting_niche(session)
        link = CanonicalRepository(session).upsert_from_discovery_result(
            company_name="Uninspected Painter",
            geography="Toronto",
            source="openstreetmap",
            raw={"id": "osm/uninspected-painter", "name": "Uninspected Painter"},
        )

        facts = BusinessAttributeRepository(session).map_for_businesses(
            [link.business_id]
        ).get(link.business_id, {})

        assert "website_status" not in facts
        assert "contact_form_present" not in facts
        assert "quote_or_booking_form_present" not in facts


def test_name_alone_does_not_merge_businesses_across_locations() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        first = canonical.upsert_from_discovery_result(
            company_name="Common Painting",
            geography="Toronto",
            source="directory_a",
            raw={},
        )
        second = canonical.upsert_from_discovery_result(
            company_name="Common Painting",
            geography="Hamilton",
            source="directory_b",
            raw={},
        )

        assert first.business_id != second.business_id
        assert second.identity_conflict is True
        assert first.business_id in second.identity_candidate_ids


def test_incompatible_shared_phone_is_created_for_review_not_merged() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        first = canonical.upsert_from_discovery_result(
            company_name="Alpha Painting",
            geography="Toronto",
            source="directory_a",
            raw={"phone": "416-555-0199"},
        )
        second = canonical.upsert_from_discovery_result(
            company_name="Beta Roofing",
            geography="Toronto",
            source="directory_b",
            raw={"phone": "416-555-0199"},
        )

        assert first.business_id != second.business_id
        assert second.identity_conflict is True
        assert second.identity_conflict_reason == "strong identifier conflicts with the business name"


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
        facts = BusinessAttributeRepository(session).map_for_businesses([link.business_id])
        assert attribute_value(facts[link.business_id][BusinessAttributeKey.WEBSITE_STATUS.value]) == "not_listed"

        canonical.record_business_evidence(
            business=session.get(BusinessAttributeModel, link.source_evidence_id).business,
            source="website_presence_check",
            raw={"website_presence": {"status": "no_website_found"}},
        )
        facts = BusinessAttributeRepository(session).map_for_businesses([link.business_id])
        assert attribute_value(facts[link.business_id][BusinessAttributeKey.WEBSITE_STATUS.value]) == "not_listed"

        canonical.upsert_from_discovery_result(
            company_name="Test Painter",
            website_url="https://testpainter.example",
            geography="Toronto",
            source="google_places",
            raw={**_source_payload("website_found_during_confirmation"), "websiteUri": "https://testpainter.example"},
        )
        facts = BusinessAttributeRepository(session).map_for_businesses([link.business_id])
        assert attribute_value(facts[link.business_id][BusinessAttributeKey.WEBSITE_STATUS.value]) == "present"
        fact = facts[link.business_id][BusinessAttributeKey.WEBSITE_STATUS.value]
        assert fact.expires_at is not None


def test_late_website_evidence_is_routed_to_existing_canonical_business() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        existing = canonical.upsert_from_discovery_result(
            company_name="Maple Air Heating & Cooling",
            website_url="https://mapleair.example",
            geography="Toronto",
            source="google_places",
            raw={
                **_source_payload(
                    "present",
                    external_id="places/maple-air-existing",
                    phone="416-555-0101",
                ),
                "displayName": {"text": "Maple Air Heating & Cooling"},
                "websiteUri": "https://mapleair.example",
            },
        )
        duplicate = canonical.upsert_from_discovery_result(
            company_name="Maple Air Heating & Cooling",
            geography="Vaughan",
            source="openstreetmap",
            raw={
                "external_id": "osm/maple-air-duplicate",
                "phone": "416-555-0202",
            },
        )
        assert duplicate.business_id != existing.business_id

        link = canonical.record_business_evidence(
            business=session.get(BusinessModel, duplicate.business_id),
            source="google_places",
            raw={
                **_source_payload(
                    "present",
                    external_id="places/maple-air-confirmed",
                    phone="416-555-0202",
                ),
                "displayName": {"text": "Maple Air Heating & Cooling"},
                "websiteUri": "https://mapleair.example",
            },
        )
        session.flush()

        assert link.business_id == existing.business_id
        assert session.get(BusinessModel, duplicate.business_id).domain is None
        assert session.get(BusinessModel, existing.business_id).domain == "mapleair.example"


def test_completed_independent_search_resolves_missing_website_fact() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        link = canonical.upsert_from_discovery_result(
            company_name="Verified Missing Painter",
            geography="Toronto",
            source="google_places",
            raw=_source_payload("no_website_listed"),
        )

        canonical.record_business_evidence(
            business=session.get(
                BusinessAttributeModel, link.source_evidence_id
            ).business,
            source="website_presence_check",
            raw={
                "website_presence": {
                    "status": "no_website_found",
                    "confirmation_attempted": True,
                    "confirmation_checks": [
                        {
                            "provider": "configured_search",
                            "status": "completed",
                            "query": '"Verified Missing Painter" Toronto',
                            "result_count": 0,
                        }
                    ],
                }
            },
        )

        facts = BusinessAttributeRepository(session).map_for_businesses([link.business_id])
        website = facts[link.business_id][BusinessAttributeKey.WEBSITE_STATUS.value]
        assert attribute_value(website) == "missing"
        assert website.attribute_score == 100


def test_unverified_no_website_found_remains_listing_gap() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        link = canonical.upsert_from_discovery_result(
            company_name="Unverified Missing Painter",
            geography="Toronto",
            source="google_places",
            raw={"website_presence": {"status": "no_website_found"}},
        )

        facts = BusinessAttributeRepository(session).map_for_businesses([link.business_id])
        website = facts[link.business_id][BusinessAttributeKey.WEBSITE_STATUS.value]
        assert attribute_value(website) == "not_listed"
        assert website.attribute_score is None


def test_verified_website_enrichment_promotes_canonical_url() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        link = canonical.upsert_from_discovery_result(
            company_name="Luke's Painting",
            geography="Toronto",
            source="google_places",
            raw=_source_payload("no_website_listed"),
        )
        business = session.get(BusinessAttributeModel, link.source_evidence_id).business

        canonical.record_business_evidence(
            business=business,
            source="company_website_seed",
            raw={
                "website_url": "https://lukekushspainting.example",
                "website_enrichment": {
                    "availability_status": "active",
                    "inspected_urls": ["https://lukekushspainting.example"],
                    "phones": [],
                },
            },
        )

        assert business.website_url == "https://lukekushspainting.example"
        facts = BusinessAttributeRepository(session).map_for_businesses([business.id])
        assert attribute_value(facts[business.id][BusinessAttributeKey.WEBSITE_STATUS.value]) == "present"


def test_missing_url_does_not_become_a_missing_website_fact() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        link = canonical.upsert_from_discovery_result(
            company_name="Unverified Painter",
            geography="Toronto",
            source="openstreetmap",
            raw={"businessStatus": "OPERATIONAL"},
        )
        business = session.get(BusinessModel, link.business_id)
        assert business is not None

        canonical.record_business_evidence(
            business=business,
            source="company_website_signal",
            raw={
                "website_url": None,
                "website_enrichment": {
                    "availability_status": "missing",
                    "availability_reason": "No website URL was available for inspection.",
                    "inspected_urls": [],
                },
            },
        )

        facts = BusinessAttributeRepository(session).map_for_businesses([business.id])
        assert attribute_value(facts[business.id][BusinessAttributeKey.WEBSITE_STATUS.value]) == (
            "unknown"
        )


def test_verified_website_replaces_stale_canonical_url() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        link = canonical.upsert_from_discovery_result(
            company_name="North Star Painting",
            geography="Toronto",
            source="google_places",
            raw=_source_payload("no_website_listed", phone="416-555-0101"),
        )
        business = session.get(BusinessModel, link.business_id)
        assert business is not None
        business.website_url = "https://wrong-company.example"
        business.domain = "wrong-company.example"
        session.flush()

        evidence = canonical.record_business_evidence(
            business=business,
            source="company_website_seed",
            raw={
                "website_url": "https://northstarpainting.example",
                "website_enrichment": {
                    "availability_status": "active",
                    "inspected_urls": ["https://northstarpainting.example"],
                    "phones": ["416-555-0101"],
                },
            },
        )

        facts = BusinessAttributeRepository(session).map_for_businesses([business.id])
        website_fact = facts[business.id][BusinessAttributeKey.WEBSITE_STATUS.value]
        assert business.website_url == "https://northstarpainting.example"
        assert business.domain == "northstarpainting.example"
        assert website_fact.source == "company_website_seed"
        assert website_fact.source_url == "https://northstarpainting.example"
        assert website_fact.evidence == {}
        assert website_fact.confidence == 95


def test_mismatched_website_enrichment_does_not_create_present_fact() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        link = canonical.upsert_from_discovery_result(
            company_name="Max Painting",
            geography="Toronto",
            source="google_places",
            raw=_source_payload("no_website_listed", phone="416-555-0101"),
        )
        business = session.get(BusinessAttributeModel, link.source_evidence_id).business

        canonical.record_business_evidence(
            business=business,
            source="company_website_seed",
            raw={
                "website_url": "https://maxpaintworks.example",
                "website_enrichment": {
                    "availability_status": "active",
                    "inspected_urls": ["https://maxpaintworks.example"],
                    "phones": ["845-555-0199"],
                    "has_contact_form": True,
                    "has_quote_form": True,
                },
            },
        )

        assert business.website_url is None
        facts = BusinessAttributeRepository(session).map_for_businesses([business.id])
        assert attribute_value(facts[business.id][BusinessAttributeKey.WEBSITE_STATUS.value]) == "not_listed"
        assert BusinessAttributeKey.CONTACT_FORM_PRESENT.value not in facts[business.id]
        assert BusinessAttributeKey.QUOTE_OR_BOOKING_FORM_PRESENT.value not in facts[business.id]


def test_reconciliation_updates_materialized_lead_fact_snapshot() -> None:
    raw_sources = [
        {
            "match_origin": "profile_sql",
            "business_attributes": {"website_status": "not_listed"},
        },
        {
            "nested": {
                "business_attributes": {"website_status": {"value": "missing"}}
            }
        },
    ]

    assert _replace_website_fact(raw_sources, "present") is True
    assert raw_sources[0]["business_attributes"]["website_status"] == "present"
    assert raw_sources[1]["nested"]["business_attributes"]["website_status"]["value"] == "present"
    assert _replace_website_fact(raw_sources, "present") is False


def test_search_contract_matches_only_current_supported_facts() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        niche = _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        missing = canonical.upsert_from_discovery_result(
            company_name="Alpha Brushworks",
            geography="Toronto",
            source="google_places",
            raw=_source_payload("missing", external_id="places/missing"),
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
                    attribute_key="website_status",
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
        current_facts = BusinessAttributeRepository(session).map_for_businesses(
            [missing.business_id]
        )[missing.business_id]
        assert attribute_value(current_facts[BusinessAttributeKey.WEBSITE_STATUS.value]) == "missing"

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
                attribute_key="google_review_count",
                operator="less_than",
                value=12,
            ),
            SearchIntentCriterion(
                id="no_quote_form",
                description="No quote form",
                mode=SearchCriterionMode.ALTERNATIVE,
                attribute_key="quote_or_booking_form_present",
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
        BusinessAttributeKey.GOOGLE_REVIEW_COUNT.value,
    }
    assert contract.semantic_any_of == ("No quote form",)
    assert contract.semantic_all_of == ("Independent business",)
    assert contract.semantic_exclusions == ("National chains and franchises",)
    assert contract.unsupported == (
        "No quote form (quote_or_booking_form_present)",
    )


def test_explicit_present_website_contract_does_not_use_opportunity_fallback() -> None:
    contract = compile_search_contract(
        _intent(
            SearchIntentCriterion(
                id="website_present",
                description="Business has a website",
                mode=SearchCriterionMode.REQUIRED,
                attribute_key="website_status",
                operator="equals",
                value="present",
            )
        )
    )

    assert [(predicate.key, predicate.value) for predicate in contract.all_of] == [
        (BusinessAttributeKey.WEBSITE_STATUS.value, "present")
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
                    attribute_key="website_status",
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


def test_unconfirmed_website_absence_is_unknown_not_rejected() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        niche = _add_painting_niche(session)
        canonical = CanonicalRepository(session)
        unresolved = canonical.upsert_from_discovery_result(
            company_name="Alpha Brushworks",
            geography="Toronto",
            source="google_places",
            raw=_source_payload("no_website_found", external_id="places/unresolved"),
        )
        contract = compile_search_contract(
            _intent(
                SearchIntentCriterion(
                    id="website_present",
                    description="Business has a website",
                    mode=SearchCriterionMode.REQUIRED,
                    attribute_key="website_status",
                    operator="equals",
                    value="present",
                )
            )
        )

        rows, decisions = BusinessIndexSearchService(
            session
        ).search_candidates_with_diagnostics(
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
            unresolved.business_id
        ]
        assert rows[0]["raw"]["search_match"] == {
            "status": "unknown",
            "reason": "Website presence has not been verified.",
        }
        assert decisions[0]["status"] == "unknown"


def _intent(*criteria: SearchIntentCriterion) -> SourceRequestIntent:
    return SourceRequestIntent(
        business_category="painting contractors",
        location="Toronto",
        criteria=list(criteria),
        search_query="painting contractors in Toronto",
        confidence=100,
        rationale="Test intent",
    )
