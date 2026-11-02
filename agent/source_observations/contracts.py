from __future__ import annotations


GOOGLE_SOURCES = frozenset({"google_places", "google_places_seed"})

COLLECTOR_SOURCES = {
    "website_http": frozenset({"company_website_signal"}),
    "website_dom": frozenset({"company_website_signal"}),
    "pagespeed_mobile": frozenset({"pagespeed_mobile"}),
    "domain_rdap": frozenset({"domain_rdap"}),
    "google_places": GOOGLE_SOURCES,
}

FACT_SOURCES = {
    "business_operational": frozenset(
        {"google_places", "google_places_seed", "openstreetmap"}
    ),
    "website_status": frozenset(
        {
            "company_website_signal",
            "company_website_seed",
            "website_presence_check",
            "google_places",
            "google_places_seed",
            "openstreetmap",
        }
    ),
    "contact_form_present": frozenset(
        {"company_website_signal", "company_website_seed"}
    ),
    "quote_or_booking_form_present": frozenset(
        {"company_website_signal", "company_website_seed"}
    ),
}


def expected_sources_for(
    *,
    fact_key: str,
    collector_key: str | None,
):
    return FACT_SOURCES.get(fact_key, COLLECTOR_SOURCES.get(collector_key or ""))
