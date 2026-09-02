from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlparse

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from db.models import ContactSuppressionModel, LeadModel
from leads.schemas import ContactPolicyStatus, SuppressionScope
from shared.utils import new_id, utcnow


SUPPRESSED_STATUSES = {
    ContactPolicyStatus.SUPPRESSED,
    ContactPolicyStatus.UNSUBSCRIBED,
    ContactPolicyStatus.BOUNCED,
}


class ContactSuppressionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_product(self, product_id: str) -> list[ContactSuppressionModel]:
        statement = (
            select(ContactSuppressionModel)
            .where(
                or_(
                    ContactSuppressionModel.product_id == product_id,
                    ContactSuppressionModel.scope == SuppressionScope.GLOBAL.value,
                )
            )
            .order_by(ContactSuppressionModel.created_at.desc())
        )
        return list(self.session.scalars(statement))

    def set_lead_policy(
        self,
        lead: LeadModel,
        *,
        status: ContactPolicyStatus,
        reason: str | None = None,
        scope: SuppressionScope = SuppressionScope.PRODUCT,
    ) -> LeadModel:
        normalized_reason = " ".join((reason or "").split()) or None
        lead.contact_policy_status = status.value
        lead.contact_policy_reason = normalized_reason
        lead.contact_policy_checked_at = utcnow()
        if status in SUPPRESSED_STATUSES:
            lead.shortlisted_at = None
            for kind, value in lead_suppression_identifiers(lead):
                self._upsert(
                    product_id=lead.product_id if scope == SuppressionScope.PRODUCT else None,
                    lead_id=lead.id,
                    scope=scope.value,
                    kind=kind,
                    value=value,
                    status=status.value,
                    reason=normalized_reason,
                    source="manual",
                )
        self.session.commit()
        self.session.refresh(lead)
        return lead

    def clear_lead_policy(self, lead: LeadModel) -> LeadModel:
        self.session.execute(
            delete(ContactSuppressionModel).where(ContactSuppressionModel.lead_id == lead.id)
        )
        lead.contact_policy_status = ContactPolicyStatus.ALLOWED.value
        lead.contact_policy_reason = None
        lead.contact_policy_checked_at = utcnow()
        self.session.commit()
        self.session.refresh(lead)
        return lead

    def apply_to_lead_model(self, lead: LeadModel, *, commit: bool = True) -> LeadModel:
        match = self.find_match_for_lead(lead)
        if match:
            lead.contact_policy_status = match.status
            lead.contact_policy_reason = match.reason
            lead.contact_policy_checked_at = utcnow()
            lead.shortlisted_at = None
        elif not lead.contact_policy_status:
            lead.contact_policy_status = ContactPolicyStatus.ALLOWED.value
            lead.contact_policy_checked_at = utcnow()
        if commit:
            self.session.commit()
            self.session.refresh(lead)
        return lead

    def find_match_for_lead(self, lead: LeadModel) -> ContactSuppressionModel | None:
        identifiers = list(lead_suppression_identifiers(lead))
        if not identifiers:
            return None
        conditions = [
            (ContactSuppressionModel.kind == kind) & (ContactSuppressionModel.value == value)
            for kind, value in identifiers
        ]
        statement = (
            select(ContactSuppressionModel)
            .where(or_(*conditions))
            .where(
                or_(
                    ContactSuppressionModel.scope == SuppressionScope.GLOBAL.value,
                    ContactSuppressionModel.product_id == lead.product_id,
                )
            )
            .order_by(ContactSuppressionModel.created_at.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def _upsert(
        self,
        *,
        product_id: str | None,
        lead_id: str,
        scope: str,
        kind: str,
        value: str,
        status: str,
        reason: str | None,
        source: str,
    ) -> ContactSuppressionModel:
        statement = (
            select(ContactSuppressionModel)
            .where(ContactSuppressionModel.scope == scope)
            .where(ContactSuppressionModel.kind == kind)
            .where(ContactSuppressionModel.value == value)
        )
        if product_id is None:
            statement = statement.where(ContactSuppressionModel.product_id.is_(None))
        else:
            statement = statement.where(ContactSuppressionModel.product_id == product_id)
        model = self.session.scalar(statement)
        if model is None:
            model = ContactSuppressionModel(
                id=new_id("suppression"),
                product_id=product_id,
                lead_id=lead_id,
                scope=scope,
                kind=kind,
                value=value,
                status=status,
                reason=reason,
                source=source,
            )
            self.session.add(model)
        else:
            model.lead_id = lead_id
            model.status = status
            model.reason = reason
            model.source = source
            model.updated_at = utcnow()
        return model


def is_blocked_contact_policy(status: ContactPolicyStatus | str | None) -> bool:
    if isinstance(status, ContactPolicyStatus):
        value = status
    elif isinstance(status, str) and status:
        try:
            value = ContactPolicyStatus(status)
        except ValueError:
            return False
    else:
        return False
    return value in SUPPRESSED_STATUSES


def lead_suppression_identifiers(lead: LeadModel) -> Iterable[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    emails = [
        lead.contact_email,
        _research_value(lead, "contact_email"),
        *(_raw_values(lead.raw_sources, _EMAIL_KEYS)),
    ]
    for email in emails:
        normalized = normalize_email(email)
        if normalized:
            key = ("email", normalized)
            if key not in seen:
                seen.add(key)
                yield key
            domain = normalize_domain(normalized)
            if domain:
                domain_key = ("domain", domain)
                if domain_key not in seen:
                    seen.add(domain_key)
                    yield domain_key

    domains = [
        lead.website_url,
        _research_value(lead, "website_url"),
        *(_raw_values(lead.raw_sources, _URL_KEYS)),
    ]
    for value in domains:
        domain = normalize_domain(value)
        if domain:
            key = ("domain", domain)
            if key not in seen:
                seen.add(key)
                yield key

    phones = [*_raw_values(lead.raw_sources, _PHONE_KEYS)]
    for phone in phones:
        normalized = normalize_phone(phone)
        if normalized:
            key = ("phone", normalized)
            if key not in seen:
                seen.add(key)
                yield key


def normalize_email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if "@" in normalized else None


def normalize_phone(value: object) -> str | None:
    if not isinstance(value, (str, int, float)):
        return None
    digits = re.sub(r"\D+", "", str(value))
    return digits if len(digits) >= 7 else None


def normalize_domain(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    if "@" in text and not text.startswith(("http://", "https://")):
        text = text.rsplit("@", 1)[1]
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = parsed.netloc or parsed.path
    host = host.split("/", 1)[0].split(":", 1)[0].removeprefix("www.")
    return host or None


def _research_value(lead: LeadModel, key: str) -> str | None:
    research = lead.research if isinstance(lead.research, dict) else {}
    value = research.get(key)
    return value if isinstance(value, str) else None


def _raw_values(raw_sources: list[dict] | None, keys: set[str]) -> list[object]:
    values: list[object] = []
    for raw in raw_sources or []:
        values.extend(_raw_values_from_record(raw, keys))
        nested = raw.get("raw") if isinstance(raw, dict) else None
        if isinstance(nested, dict):
            values.extend(_raw_values_from_record(nested, keys))
    return values


def _raw_values_from_record(raw: dict, keys: set[str]) -> list[object]:
    return [raw[key] for key in keys if raw.get(key)]


_EMAIL_KEYS = {
    "email",
    "contact_email",
    "contactEmail",
    "sellerEmail",
    "ownerEmail",
}
_URL_KEYS = {
    "url",
    "website",
    "website_url",
    "websiteUri",
    "listingUrl",
}
_PHONE_KEYS = {
    "normalized_contact_phone",
    "contact_phone",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "phone",
    "phoneNumber",
    "phone_number",
    "telephone",
    "contactPhone",
    "sellerPhone",
    "ownerPhone",
}
