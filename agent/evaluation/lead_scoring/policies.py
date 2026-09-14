from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from evaluation.lead_scoring.signals import (
    cached_phone,
    enrichment_signals,
    evidence_text,
    has_contact_form,
    has_quote_signal,
    raw_payload,
    target_terms,
    website_enrichment,
)
from leads.schemas import AgentFitStatus, ContactVerificationStatus, LeadRead, QualificationScoreBreakdown
from products.schemas import ProductRead


QUOTE_PROBLEM_TERMS = {
    "quote",
    "quotes",
    "quoting",
    "estimate",
    "estimates",
    "estimating",
    "pricing",
    "price",
    "walkthrough",
    "walkthroughs",
    "site visit",
    "on-site",
    "onsite",
}

PROBLEM_SIGNAL_TERM_GROUPS = (
    QUOTE_PROBLEM_TERMS,
    {
        "booking",
        "bookings",
        "schedule",
        "scheduling",
        "appointment",
        "appointments",
        "dispatch",
    },
    {
        "invoice",
        "invoices",
        "invoicing",
        "payment",
        "payments",
        "billing",
    },
    {
        "inventory",
        "stock",
        "fulfillment",
        "shipping",
        "delivery",
    },
)


def score_breakdown(
    *,
    product: ProductRead,
    row: dict[str, Any],
    lead: LeadRead,
) -> QualificationScoreBreakdown:
    fit_score = problem_fit_score(product=product, row=row, lead=lead)
    reachability_score = reachability_score_for(row=row, lead=lead)
    source_quality_score = source_quality_score_for(row=row, lead=lead)
    notes = ["Cached fit is based on category/location/business evidence, not contactability."]
    if lead.contact_email:
        notes.append("Reachability includes a public email signal.")
    if cached_phone(row):
        notes.append("Reachability includes a public phone signal.")
    if has_quote_signal(row):
        notes.append("Problem evidence includes a public quote or estimate signal.")
    return QualificationScoreBreakdown(
        fit_score=fit_score,
        reachability_score=reachability_score,
        source_quality_score=source_quality_score,
        scoring_notes=notes,
    )


def final_fit_score(
    *,
    score_breakdown: QualificationScoreBreakdown,
    disqualifiers: list[str],
) -> int:
    if disqualifiers:
        return min(35, score_breakdown.fit_score)
    score = round((score_breakdown.fit_score * 0.75) + (score_breakdown.source_quality_score * 0.25))
    return max(0, min(95, score))


def fit_status(
    *,
    score_breakdown: QualificationScoreBreakdown,
    disqualifiers: list[str],
) -> AgentFitStatus:
    if disqualifiers:
        return AgentFitStatus.NOT_FIT
    if score_breakdown.source_quality_score < 55 or score_breakdown.fit_score < 50:
        return AgentFitStatus.NOT_FIT
    if score_breakdown.source_quality_score >= 65 and score_breakdown.fit_score >= 80:
        return AgentFitStatus.GOOD_FIT
    if score_breakdown.fit_score >= 65:
        return AgentFitStatus.MAYBE
    return AgentFitStatus.NOT_FIT


def qualification_rationale(
    *,
    product: ProductRead,
    lead: LeadRead,
    score_breakdown: QualificationScoreBreakdown,
    disqualifiers: list[str],
) -> str:
    if disqualifiers:
        return (
            f"{lead.company_name} was not treated as a fit for {product.product_name} "
            f"because cached evidence raised: {', '.join(disqualifiers[:2])}."
        )
    return (
        f"{lead.company_name} matched cached business evidence for {product.product_name}; "
        f"fit {score_breakdown.fit_score}, source quality {score_breakdown.source_quality_score}, "
        f"reachability {score_breakdown.reachability_score}."
    )


def problem_fit_score(*, product: ProductRead, row: dict[str, Any], lead: LeadRead) -> int:
    enrichment = website_enrichment(row)
    service_signals = [signal for signal in enrichment.get("service_signals", []) if isinstance(signal, str)]
    text = evidence_text(row=row, lead=lead, extra=service_signals)
    matched_target_terms = sum(1 for term in target_terms(product) if term in text)

    score = 30
    score += min(matched_target_terms * 7, 30)
    score += min(len(service_signals) * 6, 18)
    if has_quote_signal(row):
        score += 15
    if product.target_geography.lower() and product.target_geography.lower() in text:
        score += 5
    if product_problem_signal_required(product) and not has_product_problem_signal(
        product=product,
        row=row,
        lead=lead,
    ):
        score = min(score, 74)
    return max(0, min(100, score))


def reachability_score_for(*, row: dict[str, Any], lead: LeadRead) -> int:
    score = 0
    if lead.contact_email:
        score += 60 if looks_like_person_email(lead.contact_email) else 40
    if cached_phone(row):
        score += 25
    if has_contact_form(row):
        score += 15
    if lead.verification_status == ContactVerificationStatus.VALID:
        score += 15
    elif lead.verification_status == ContactVerificationStatus.RISKY:
        score -= 10
    elif lead.verification_status == ContactVerificationStatus.INVALID:
        score -= 35
    return max(0, min(100, score))


def source_quality_score_for(*, row: dict[str, Any], lead: LeadRead) -> int:
    raw = raw_payload(row)
    source = str(row.get("source") or raw.get("source") or raw.get("provider_id") or "")
    enrichment = website_enrichment(row)

    score = 35
    if raw.get("semantic_cache_hit"):
        score += 5
    if lead.website_url:
        score += 20
    if raw.get("canonical_business_id"):
        score += 20
    if source == "google_places":
        score += 15
    if enrichment.get("inspected_urls"):
        score += 10
    return max(0, min(100, score))


def disqualifiers(*, product: ProductRead, row: dict[str, Any], lead: LeadRead) -> list[str]:
    raw = raw_payload(row)
    source = str(row.get("source") or raw.get("source") or raw.get("provider_id") or "")
    url = str(row.get("url") or lead.website_url or "")
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    text = evidence_text(row=row, lead=lead, extra=enrichment_signals(row))
    reasons: list[str] = []

    if not has_business_identity(row=row, lead=lead):
        reasons.append("No stable business identity found.")
    if host_matches(host, ("linkedin.com", "facebook.com", "instagram.com", "youtube.com", "x.com")):
        reasons.append("Social/content host, not a business website.")
    if source != "google_places" and (
        host_matches(host, ("yelp.", "angi.", "homeadvisor.", "thumbtack.", "yellowpages.", "houzz."))
        or contains_any(text, ("directory", "list of", "find a", "best ", "top "))
    ):
        reasons.append("Directory, list, review, or aggregator page.")
    if contains_any(text, ("salary", "salaries", "pay scale", "compensation", "wage")):
        reasons.append("Salary or compensation page.")
    if contains_any(text, ("jobs", "career", "careers", "hiring", "employment", "resume", "recruit")) or any(
        part in path for part in ("/jobs", "/careers", "/hiring")
    ):
        reasons.append("Job or career page.")
    if contains_any(text, ("blog", "article", "guide", "how to", "template", "podcast", "watch video")) or any(
        part in path for part in ("/blog", "/article", "/articles", "/news", "/resources", "/learn")
    ):
        reasons.append("Content page, not a customer business.")
    if looks_like_solution_vendor(text, product):
        reasons.append("Vendor, software, or competitor page rather than a potential customer.")
    if wrong_geography(product=product, lead=lead, text=text):
        reasons.append("Outside target geography.")

    return list(dict.fromkeys(reasons))[:4]


def missing_evidence(
    *,
    product: ProductRead,
    row: dict[str, Any],
    lead: LeadRead,
    score_breakdown: QualificationScoreBreakdown,
) -> list[str]:
    missing: list[str] = []
    if score_breakdown.fit_score < 65:
        missing.append("Specific product/problem fit evidence is weak.")
    if score_breakdown.source_quality_score < 65:
        missing.append("Source needs stronger business-entity evidence.")
    if not lead.contact_email:
        missing.append("Direct email not found.")
    elif lead.verification_status == ContactVerificationStatus.UNVERIFIED:
        missing.append("Email deliverability not verified.")
    if product_problem_signal_required(product) and not has_product_problem_signal(
        product=product,
        row=row,
        lead=lead,
    ):
        missing.append(problem_missing_evidence_label(product))
    return missing


def looks_like_person_email(email: str) -> bool:
    local_part = email.split("@", 1)[0].lower().strip()
    generic_prefixes = {
        "admin",
        "booking",
        "contact",
        "customerservice",
        "hello",
        "help",
        "info",
        "office",
        "quotes",
        "sales",
        "service",
        "support",
        "team",
    }
    normalized = re.sub(r"[^a-z]", "", local_part)
    return bool(normalized and normalized not in generic_prefixes and len(normalized) > 2)


def has_business_identity(*, row: dict[str, Any], lead: LeadRead) -> bool:
    raw = raw_payload(row)
    company_name = lead.company_name.strip().lower()
    generic_names = {
        "",
        "painting",
        "painting services",
        "painters",
        "local painters",
        "home services",
        "service providers",
    }
    has_specific_name = company_name not in generic_names and len(company_name) >= 4
    return bool(
        has_specific_name
        and (
            lead.website_url
            or lead.contact_email
            or cached_phone(row)
            or raw.get("address")
            or raw.get("formattedAddress")
            or raw.get("canonical_business_id")
        )
    )


def looks_like_solution_vendor(text: str, product: ProductRead) -> bool:
    target_customer = product.target_customer.lower()
    software_target_terms = (
        "software",
        "saas",
        "technology",
        "tech company",
        "developer",
        "engineering",
        "it team",
        "startup",
    )
    if any(term in target_customer for term in software_target_terms):
        return False
    return contains_any(
        text,
        (
            "software",
            "app",
            "apps",
            "platform",
            "crm",
            "cpq",
            "automation",
            "quote software",
            "estimating software",
            "lead generation",
        ),
    )


def wrong_geography(*, product: ProductRead, lead: LeadRead, text: str) -> bool:
    target = product.target_geography.lower().strip()
    if not target or target in {"global", "worldwide", "united states", "canada", "united states, canada"}:
        return False
    geography = (lead.geography or "").lower()
    terms = {
        token
        for token in re.findall(r"[a-z][a-z0-9]+", target)
        if len(token) >= 4 and token not in {"area", "metro", "region"}
    }
    if not terms:
        return False
    evidence = f"{geography} {text}"
    acceptable_terms = set(terms)
    if {"toronto", "gta"} & terms:
        acceptable_terms.update(
            {
                "ajax",
                "brampton",
                "etobicoke",
                "markham",
                "mississauga",
                "north york",
                "oakville",
                "oshawa",
                "pickering",
                "richmond hill",
                "scarborough",
                "vaughan",
            }
        )
    return not any(term in evidence for term in acceptable_terms)


def product_problem_signal_required(product: ProductRead) -> bool:
    return bool(product_problem_terms(product))


def has_product_problem_signal(*, product: ProductRead, row: dict[str, Any], lead: LeadRead) -> bool:
    terms = product_problem_terms(product)
    if not terms:
        return True
    if terms & QUOTE_PROBLEM_TERMS:
        return has_quote_signal(row)
    text = evidence_text(row=row, lead=lead, extra=enrichment_signals(row))
    return any(term in text for term in terms)


def product_problem_terms(product: ProductRead) -> set[str]:
    text = product_problem_text(product)
    terms: set[str] = set()
    for group in PROBLEM_SIGNAL_TERM_GROUPS:
        if any(term in text for term in group):
            terms.update(group)
    return terms


def product_problem_text(product: ProductRead) -> str:
    criteria_text = " ".join(
        " ".join(filter(None, [criterion.label, criterion.description or ""]))
        for criterion in product.qualification_criteria
    )
    return " ".join(
        [
            product.product_description,
            product.problem_being_solved,
            product.value_proposition,
            criteria_text,
        ]
    ).lower()


def problem_missing_evidence_label(product: ProductRead) -> str:
    terms = product_problem_terms(product)
    if terms & QUOTE_PROBLEM_TERMS:
        return "Explicit quote or estimate workflow signal not found."
    return "Specific product/problem signal not found."


def host_matches(host: str, blocked_hosts: tuple[str, ...]) -> bool:
    return any(host == blocked.rstrip(".") or blocked in host for blocked in blocked_hosts)


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
