from __future__ import annotations

import re
from typing import Any

from leads.schemas import LeadRead
from products.schemas import ProductRead
from shared.utils import truncate


def raw_payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("raw")
    return raw if isinstance(raw, dict) else {}


def website_enrichment(row: dict[str, Any]) -> dict[str, Any]:
    enrichment = raw_payload(row).get("website_enrichment")
    return enrichment if isinstance(enrichment, dict) else {}


def cached_signals(*, row: dict[str, Any], lead: LeadRead) -> list[str]:
    raw = raw_payload(row)
    enrichment = website_enrichment(row)
    signals: list[str] = []
    signals.extend(signal for signal in raw.get("signals", []) if isinstance(signal, str))
    signals.extend(signal for signal in enrichment.get("service_signals", []) if isinstance(signal, str))
    signals.extend(signal for signal in enrichment.get("quote_signals", []) if isinstance(signal, str))
    if enrichment.get("has_quote_form"):
        signals.append("quote or estimate form")
    if enrichment.get("has_contact_form"):
        signals.append("contact form")
    if lead.contact_email:
        signals.append("public email")
    if cached_phone(row):
        signals.append("public phone")
    if not signals and lead.description:
        signals.append(truncate(lead.description, 120))
    return list(dict.fromkeys(signals))[:8]


def has_quote_signal(row: dict[str, Any]) -> bool:
    enrichment = website_enrichment(row)
    return bool(enrichment.get("has_quote_form") or enrichment.get("quote_signals"))


def has_contact_form(row: dict[str, Any]) -> bool:
    return bool(website_enrichment(row).get("has_contact_form"))


def cached_phone(row: dict[str, Any]) -> str | None:
    raw = raw_payload(row)
    for source in (row, raw):
        for key in ("phone", "contact_phone", "nationalPhoneNumber", "internationalPhoneNumber"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def cached_sources(*, row: dict[str, Any], lead: LeadRead) -> list[str]:
    enrichment = website_enrichment(row)
    sources = []
    if lead.website_url:
        sources.append(lead.website_url)
    if isinstance(enrichment.get("inspected_urls"), list):
        sources.extend(url for url in enrichment["inspected_urls"] if isinstance(url, str))
    return list(dict.fromkeys(sources))[:5]


def cached_business_type(*, product: ProductRead, row: dict[str, Any], lead: LeadRead) -> str:
    enrichment = website_enrichment(row)
    service_signals = enrichment.get("service_signals")
    if isinstance(service_signals, list) and service_signals:
        return ", ".join(str(signal) for signal in service_signals[:3])
    return lead.description or product.target_customer


def evidence_text(*, row: dict[str, Any], lead: LeadRead, extra: list[str]) -> str:
    raw = raw_payload(row)
    parts = [
        lead.company_name,
        lead.description,
        lead.geography,
        str(row.get("title") or ""),
        str(row.get("snippet") or ""),
        str(raw.get("business_type") or ""),
        " ".join(extra),
    ]
    return " ".join(part for part in parts if part).lower()


def enrichment_signals(row: dict[str, Any]) -> list[str]:
    enrichment = website_enrichment(row)
    signals: list[str] = []
    for key in ("service_signals", "quote_signals", "contact_signals"):
        signals.extend(signal for signal in enrichment.get(key, []) if isinstance(signal, str))
    return signals


def target_terms(product: ProductRead) -> set[str]:
    text = " ".join(
        [
            product.target_customer,
            product.problem_being_solved,
            " ".join(criterion.label for criterion in product.qualification_criteria),
        ]
    ).lower()
    stopwords = {
        "with",
        "that",
        "this",
        "from",
        "they",
        "their",
        "about",
        "have",
        "need",
        "needs",
        "customer",
        "customers",
        "business",
        "businesses",
        "professional",
        "professionals",
        "service",
        "services",
        "provider",
        "providers",
    }
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9]+", text)
        if len(token) > 2 and token not in stopwords
    }
