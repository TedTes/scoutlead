from __future__ import annotations

import re
from urllib.parse import urlparse

from discovery.schemas import CandidateAssessment, DiscoveryCandidateType
from products.schemas import ProductRead
from tools.search import SearchResult


BLOCKED_SOCIAL_HOSTS = {
    "youtube.com",
    "youtu.be",
    "vimeo.com",
    "medium.com",
    "reddit.com",
    "quora.com",
    "wikipedia.org",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
}

DIRECTORY_HOST_HINTS = (
    "yelp.",
    "angi.",
    "angieslist.",
    "homeadvisor.",
    "thumbtack.",
    "bbb.",
    "yellowpages.",
    "mapquest.",
    "houzz.",
    "nextdoor.",
    "porch.",
    "expertise.",
)

SALARY_TERMS = (
    "salary",
    "salaries",
    "pay scale",
    "payscale",
    "compensation",
    "wage",
    "wages",
    "cost of living",
)

JOB_TERMS = (
    "job",
    "jobs",
    "career",
    "careers",
    "hiring",
    "employment",
    "resume",
    "recruit",
)

CONTENT_TERMS = (
    "blog",
    "article",
    "guide",
    "how to",
    "tips",
    "strategies",
    "whitepaper",
    "template",
    "podcast",
    "watch",
    "video",
)

DIRECTORY_TERMS = (
    "best ",
    "top ",
    "near me",
    "reviews",
    "review",
    "directory",
    "list of",
    "find a",
)

VENDOR_TERMS = (
    "software",
    "app",
    "apps",
    "platform",
    "tool",
    "tools",
    "saas",
    "crm",
    "cpq",
    "automation",
    "solution",
    "solutions",
    "online approvals",
    "in seconds",
    "in minutes",
)

BUSINESS_TERMS = (
    "llc",
    "inc",
    "co.",
    "company",
    "services",
    "contractor",
    "contractors",
    "painting",
    "paint",
    "plumbing",
    "roofing",
    "hvac",
    "landscaping",
    "electric",
    "construction",
    "repair",
    "remodeling",
    "free estimate",
    "request a quote",
    "contact us",
)


def assess_discovery_candidate(result: SearchResult, product: ProductRead) -> CandidateAssessment:
    if not result.url:
        return CandidateAssessment(
            candidate_type=DiscoveryCandidateType.UNKNOWN,
            confidence=20,
            rejection_reason="Search result has no URL.",
        )

    parsed = urlparse(result.url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    title = result.title.lower()
    snippet = (result.snippet or "").lower()
    text = " ".join([title, snippet, host, path.replace("-", " ").replace("_", " ")])

    if _host_matches(host, BLOCKED_SOCIAL_HOSTS):
        return _reject(DiscoveryCandidateType.SOCIAL, 95, "Social/content host, not a business website.")

    if _contains_any(text, SALARY_TERMS):
        return _reject(DiscoveryCandidateType.SALARY, 95, "Salary or compensation page, not a customer business.")

    if _contains_any(text, JOB_TERMS) or any(part in path for part in ("/jobs", "/careers", "/hiring")):
        return _reject(DiscoveryCandidateType.JOB, 90, "Job or career page, not a customer business.")

    if any(hint in host for hint in DIRECTORY_HOST_HINTS) or _contains_any(text, DIRECTORY_TERMS):
        return _reject(DiscoveryCandidateType.DIRECTORY, 90, "Directory, list, review, or aggregator page.")

    if _contains_any(text, CONTENT_TERMS) or any(
        part in path for part in ("/blog", "/article", "/articles", "/news", "/resources", "/learn")
    ):
        return _reject(DiscoveryCandidateType.CONTENT, 90, "Content page, not a customer business.")

    if _is_vendor_or_competitor(text, product):
        return _reject(
            DiscoveryCandidateType.VENDOR,
            90,
            "Product, software, vendor, or competitor page rather than a potential customer.",
        )

    confidence = _business_confidence(text, result, product)
    if confidence >= 65:
        return CandidateAssessment(candidate_type=DiscoveryCandidateType.TARGET_BUSINESS, confidence=confidence)

    return CandidateAssessment(
        candidate_type=DiscoveryCandidateType.UNKNOWN,
        confidence=confidence,
        rejection_reason="Result does not have enough evidence of being a target customer business.",
    )


def _reject(
    candidate_type: DiscoveryCandidateType,
    confidence: int,
    reason: str,
) -> CandidateAssessment:
    return CandidateAssessment(
        candidate_type=candidate_type,
        confidence=confidence,
        rejection_reason=reason,
    )


def _host_matches(host: str, blocked_hosts: set[str]) -> bool:
    return host in blocked_hosts or any(host.endswith(f".{blocked}") for blocked in blocked_hosts)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _is_vendor_or_competitor(text: str, product: ProductRead) -> bool:
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
    return _contains_any(text, VENDOR_TERMS)


def _business_confidence(text: str, result: SearchResult, product: ProductRead) -> int:
    confidence = 35
    target_terms = _target_terms(product)
    matched_target_terms = sum(1 for term in target_terms if term in text)
    matched_business_terms = sum(1 for term in BUSINESS_TERMS if term in text)

    confidence += min(matched_target_terms * 10, 30)
    confidence += min(matched_business_terms * 8, 24)

    if result.contact_email:
        confidence += 10
    if "contact" in text:
        confidence += 6
    if "quote" in text or "estimate" in text:
        confidence += 6

    return max(0, min(confidence, 95))


def _target_terms(product: ProductRead) -> set[str]:
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
        "united",
        "states",
    }
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9]+", text)
        if len(token) >= 4 and token not in stopwords
    }
