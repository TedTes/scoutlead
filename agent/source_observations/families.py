from __future__ import annotations


DERIVED_INSPECTION_SOURCES = frozenset(
    {
        "company_website_seed",
        "company_website_signal",
        "domain_rdap",
        "pagespeed_mobile",
        "website_presence_check",
    }
)
VERIFICATION_SOURCES = frozenset({"configured_search"})


def source_family(source: str | None) -> str:
    normalized = str(source or "").strip().lower()
    if normalized in DERIVED_INSPECTION_SOURCES:
        return "derived_inspection"
    if normalized in VERIFICATION_SOURCES:
        return "verification"
    if normalized:
        return "independent_discovery"
    return "unknown"


def independent_source_count(sources: set[str]) -> int:
    return sum(source_family(source) == "independent_discovery" for source in sources)
