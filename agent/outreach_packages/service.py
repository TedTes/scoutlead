from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    AudienceResultModel,
    AudienceRunModel,
    BusinessModel,
    DemoSiteModel,
    OutreachPackageModel,
    ProductModel,
    TerritoryModel,
    WorkspaceModel,
)
from outreach_packages.schemas import (
    OutreachEvidence,
    OutreachPackageContent,
    OutreachPackageRead,
    OutreachPackageUpdate,
)
from outreach_packages.templates import OutreachTemplateContext, render_outreach
from shared.errors import NotFoundError, ValidationError, WorkflowBoundaryError
from shared.utils import new_id


TEMPLATE_VERSION = 1


class OutreachPackageService:
    def __init__(
        self,
        session: Session,
        *,
        workspace_id: str | None,
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def find_for_result(self, result_id: str) -> OutreachPackageRead | None:
        result, _, _, business, _ = self._context(result_id)
        row = self.session.scalar(
            select(OutreachPackageModel).where(
                OutreachPackageModel.workspace_id == self.workspace_id,
                OutreachPackageModel.audience_result_id == result.id,
            )
        )
        return self._read(row, business, result) if row is not None else None

    def generate(self, result_id: str) -> OutreachPackageRead:
        result, audience, product, business, workspace = self._context(result_id)
        if result.shortlisted_at is None:
            raise WorkflowBoundaryError(
                "Shortlist this business before preparing outreach.",
                {"result_id": result_id},
            )
        existing = self.session.scalar(
            select(OutreachPackageModel).where(
                OutreachPackageModel.workspace_id == self.workspace_id,
                OutreachPackageModel.audience_result_id == result.id,
            )
        )
        if existing is not None:
            return self._read(existing, business, result)

        snapshot = result.match_snapshot or {}
        profile_match = _profile_match(snapshot)
        matched = _outreach_eligible_matched_signals(profile_match)
        if not matched:
            raise WorkflowBoundaryError(
                "A verified opportunity is required before preparing outreach.",
                {
                    "result_id": result_id,
                    "user_message": "Collect or request an opportunity signal for this business first.",
                },
            )

        evidence = [_evidence(item) for item in matched[:6]]
        observation = evidence[0].statement
        raw = snapshot.get("raw") if isinstance(snapshot.get("raw"), dict) else {}
        contact_url = _find_string(raw, _CONTACT_URL_KEYS)
        email = _optional_string(snapshot.get("contact_email")) or _find_string(raw, _EMAIL_KEYS)
        demo = self.session.scalar(
            select(DemoSiteModel).where(
                DemoSiteModel.workspace_id == self.workspace_id,
                DemoSiteModel.audience_result_id == result.id,
                DemoSiteModel.status == "published",
            )
        )
        demo_path = f"/demo/{demo.share_token}" if demo is not None else None
        signature = (
            (workspace.sender_legal_name if workspace else None)
            or (workspace.sender_contact if workspace else None)
            or product.product_name
        )
        generated = render_outreach(
            OutreachTemplateContext(
                business_name=business.display_name,
                category=business.category_key,
                market=audience.city or audience.market_key,
                evidence=evidence[0],
                offer=product.offer_summary or product.value_proposition or product.product_name,
                call_to_action=product.outreach_objective,
                signature=signature,
                demo_path=demo_path,
            )
        )
        content = OutreachPackageContent(
            observation=observation,
            evidence=evidence,
            message=generated.message,
            call=generated.call if business.phone else None,
            form=generated.form if contact_url else None,
            email=generated.email if email else None,
            demo_path=demo_path,
        )
        row = OutreachPackageModel(
            id=new_id("outreach_package"),
            workspace_id=self.workspace_id,
            audience_result_id=result.id,
            business_id=result.business_id,
            content=content.model_dump(),
            provider="template",
            model=None,
            usage={},
            prompt_version=TEMPLATE_VERSION,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self._read(row, business, result)

    def update(self, package_id: str, data: OutreachPackageUpdate) -> OutreachPackageRead:
        row = self._owned(package_id)
        result, _, _, business, _ = self._context(row.audience_result_id)
        original = OutreachPackageContent.model_validate(row.content)
        if data.content.observation != original.observation or data.content.evidence != original.evidence:
            raise ValidationError("Verified outreach evidence cannot be edited in a draft update.")
        row.content = data.content.model_dump()
        self.session.commit()
        self.session.refresh(row)
        return self._read(row, business, result)

    def _owned(self, package_id: str) -> OutreachPackageModel:
        row = self.session.get(OutreachPackageModel, package_id)
        if row is None or row.workspace_id != self.workspace_id:
            raise NotFoundError("outreach package not found", {"package_id": package_id})
        return row

    def _context(self, result_id: str):
        result = self.session.get(AudienceResultModel, result_id)
        run = self.session.get(AudienceRunModel, result.run_id) if result else None
        audience = self.session.get(TerritoryModel, result.audience_id) if result else None
        if result is None or run is None or audience is None or run.workspace_id != self.workspace_id:
            raise NotFoundError("audience result not found", {"result_id": result_id})
        product = self.session.get(ProductModel, audience.product_id)
        business = self.session.get(BusinessModel, result.business_id)
        if product is None or business is None:
            raise NotFoundError("outreach context not found", {"result_id": result_id})
        workspace = self.session.get(WorkspaceModel, self.workspace_id) if self.workspace_id else None
        return result, audience, product, business, workspace

    def _read(
        self,
        row: OutreachPackageModel,
        business: BusinessModel,
        result: AudienceResultModel,
    ) -> OutreachPackageRead:
        content = OutreachPackageContent.model_validate(row.content)
        snapshot = result.match_snapshot or {}
        raw = snapshot.get("raw") if isinstance(snapshot.get("raw"), dict) else {}
        email = _optional_string(snapshot.get("contact_email")) or _find_string(raw, _EMAIL_KEYS)
        contact_url = _find_string(raw, _CONTACT_URL_KEYS)
        channels = ["message"]
        if content.call and business.phone:
            channels.append("call")
        if content.form and contact_url:
            channels.append("form")
        if content.email and email:
            channels.append("email")
        return OutreachPackageRead(
            id=row.id,
            audience_result_id=row.audience_result_id,
            business_id=row.business_id,
            business_name=business.display_name,
            website_url=business.website_url,
            phone=business.phone,
            email=email,
            contact_url=contact_url,
            channels=channels,
            content=content,
            provider=row.provider,
            model=row.model,
            usage=row.usage or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


_CONTACT_URL_KEYS = {
    "contact_url",
    "contacturl",
    "contactpageurl",
    "contact_page_url",
    "quote_url",
    "quoteurl",
    "booking_url",
    "bookingurl",
}
_EMAIL_KEYS = {"contact_email", "email", "emailaddress", "email_address"}


def _profile_match(snapshot: dict[str, Any]) -> dict[str, Any]:
    raw = snapshot.get("raw") if isinstance(snapshot.get("raw"), dict) else {}
    value = raw.get("profile_match")
    return value if isinstance(value, dict) else {}


def _outreach_eligible_matched_signals(
    profile_match: dict[str, Any],
) -> list[dict[str, Any]]:
    matched = [
        item
        for item in profile_match.get("matched_signals") or []
        if isinstance(item, dict)
    ]
    signal_details = profile_match.get("signals")
    details = signal_details if isinstance(signal_details, dict) else {}
    confirmed = []
    grounded_listing_gaps = []
    for item in matched:
        signal_key = str(item.get("signal_key") or "")
        detail = details.get(signal_key)
        detail_confidence = (
            detail.get("confidence") if isinstance(detail, dict) else None
        )
        confidence = item.get("confidence") or detail_confidence
        is_listed_website_gap = (
            signal_key == "website_status"
            and item.get("value") == "not_listed"
            and confidence == "possible"
        )
        if confidence == "confirmed":
            confirmed.append(item)
        elif is_listed_website_gap:
            grounded_listing_gaps.append(item)
    if confirmed or grounded_listing_gaps:
        return [*confirmed, *grounded_listing_gaps]
    if int(profile_match.get("confirmed_signal_count") or 0) >= len(matched):
        return matched
    return []


def _evidence(item: dict[str, Any]) -> OutreachEvidence:
    key = str(item.get("signal_key") or "opportunity")
    value = item.get("value")
    label = key.replace("_", " ").strip().capitalize()
    statements = {
        "website_status": (
            "The latest business listing does not include a website."
            if value == "not_listed"
            else f"The latest website status is {str(value).replace('_', ' ')}."
        ),
        "website_unavailable": "The business website was unavailable during the latest check.",
        "no_quote_flow": "No quote or booking flow was found in the latest website check.",
        "no_contact_form": "No contact form was found in the latest website check.",
        "mobile_viewport_missing": "The latest website check did not find a mobile viewport declaration.",
        "uses_http": "The latest website check found that the site is not using HTTPS.",
    }
    if key == "reviews_under_15":
        statement = f"The business has {int(value or 0)} public reviews in the latest record."
    else:
        statement = statements.get(key, f"The latest check confirmed {label.lower()}.")
    return OutreachEvidence(signal_key=key, label=label, statement=statement, value=value)


def _find_string(value: object, keys: set[str]) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in keys:
                found = _optional_string(nested)
                if found:
                    return found
        for nested in value.values():
            found = _find_string(nested, keys)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_string(nested, keys)
            if found:
                return found
    return None


def _optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
