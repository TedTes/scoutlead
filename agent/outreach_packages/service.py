from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.llm import LLMClient
from audience_runs.outreach import AudienceOutreachService
from campaigns.schemas import OutreachChannel

from db.models import (
    AudienceResultModel,
    AudienceRunModel,
    BusinessModel,
    OutreachPackageModel,
    ProductModel,
    TerritoryModel,
    WorkspaceModel,
)
from outreach_packages.schemas import (
    DraftAlternative,
    OutreachAnalyticsRead,
    OutreachEvidence,
    OutreachEventCreate,
    OutreachEventRead,
    OutreachPackageContent,
    OutreachPackageRead,
    OutreachPackageUpdate,
    OutreachAISuggestionRequest,
    OutreachResponseClassification,
    OutreachResponseClassifyRequest,
    CallDraft,
    EmailDraft,
    WrittenDraft,
)
from outreach_packages.ai import OpenAIPhrasingAdapter, ResponseClassifier
from outreach_packages.playbooks import PlaybookRepository
from outreach_packages.policy import OutreachPolicyValidator
from outreach_packages.repository import OutreachEventRepository, OutreachPlaybookRepository
from outreach_packages.templates import OutreachTemplateContext, render_outreach
from messages.repository import MessageRepository
from messages.schemas import MessageRead, OutreachDraft
from shared.errors import ConfigurationError, NotFoundError, ValidationError, WorkflowBoundaryError
from shared.utils import new_id


TEMPLATE_VERSION = 6


class OutreachPackageService:
    def __init__(
        self,
        session: Session,
        *,
        workspace_id: str | None,
        llm: LLMClient | None = None,
        ai_mode: str = "off",
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.llm = llm
        self.ai_mode = ai_mode

    def find_for_result(self, result_id: str) -> OutreachPackageRead | None:
        result, audience, product, business, workspace = self._context(result_id)
        row = self.session.scalar(
            select(OutreachPackageModel).where(
                OutreachPackageModel.workspace_id == self.workspace_id,
                OutreachPackageModel.audience_result_id == result.id,
            )
        )
        if row is not None and (
            _should_refresh_template(row) or _needs_strategy_upgrade(row)
        ):
            fresh = self._render_content(
                result, audience, product, business, workspace
            )
            row.content = _upgrade_content(row, fresh).model_dump()
            row.prompt_version = TEMPLATE_VERSION
            self.session.commit()
            self.session.refresh(row)
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
            if _should_refresh_template(existing) or _needs_strategy_upgrade(existing):
                fresh = self._render_content(
                    result, audience, product, business, workspace
                )
                existing.content = _upgrade_content(existing, fresh).model_dump()
                existing.prompt_version = TEMPLATE_VERSION
                self.session.commit()
                self.session.refresh(existing)
            return self._read(existing, business, result)

        content = self._render_content(result, audience, product, business, workspace)
        row = OutreachPackageModel(
            id=new_id("outreach_package"),
            workspace_id=self.workspace_id,
            audience_result_id=result.id,
            business_id=result.business_id,
            content=content.model_dump(),
            provider=(
                "openai"
                if content.strategy and content.strategy.phrasing_provider == "openai"
                else "template"
            ),
            model=getattr(self.llm, "model", None) if content.strategy and content.strategy.phrasing_provider == "openai" else None,
            usage={},
            prompt_version=TEMPLATE_VERSION,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self._read(row, business, result)

    def _render_content(
        self,
        result: AudienceResultModel,
        audience: TerritoryModel,
        product: ProductModel,
        business: BusinessModel,
        workspace: WorkspaceModel | None,
    ) -> OutreachPackageContent:

        snapshot = result.match_snapshot or {}
        profile_match = _profile_match(snapshot)
        matched = _outreach_eligible_matched_signals(profile_match)
        if not matched:
            raise WorkflowBoundaryError(
                "A verified opportunity is required before preparing outreach.",
                {
                    "result_id": result.id,
                    "user_message": "Collect or request an opportunity signal for this business first.",
                },
            )

        evidence = [_evidence(item) for item in matched[:6]]
        matched_services = [
            item
            for item in profile_match.get("matched_services") or []
            if isinstance(item, dict)
        ]
        catalog = OutreachPlaybookRepository(self.session).catalog()
        playbooks = PlaybookRepository(catalog)
        playbook_match = playbooks.resolve(
            service_keys=list(audience.service_keys or []),
            matched_services=matched_services,
            evidence=evidence,
        )
        if playbook_match is None:
            raise WorkflowBoundaryError(
                "No supported outreach playbook matches this opportunity.",
                {
                    "result_id": result.id,
                    "service_keys": list(audience.service_keys or []),
                    "signal_keys": [item.signal_key for item in evidence],
                    "user_message": "Review this opportunity manually before contacting the business.",
                },
            )
        stable_key = f"{result.id}:{business.id}"
        strategy = playbooks.strategy_for(
            playbook_match,
            stable_key=stable_key,
            trade_key=business.category_key or "default",
        )
        primary_evidence = playbook_match.evidence.model_copy(
            update={"statement": strategy.evidence_statement}
        )
        evidence = [
            primary_evidence,
            *(item for item in evidence if item is not playbook_match.evidence),
        ][:6]
        observation = strategy.evidence_statement
        raw = snapshot.get("raw") if isinstance(snapshot.get("raw"), dict) else {}
        contact_url = _find_string(raw, _CONTACT_URL_KEYS)
        email = _optional_string(snapshot.get("contact_email")) or _find_string(raw, _EMAIL_KEYS)
        signature = (
            (workspace.sender_legal_name if workspace else None)
            or (workspace.sender_contact if workspace else None)
            or product.product_name
        )
        template_context = OutreachTemplateContext(
            business_name=business.display_name,
            strategy=strategy,
            signature=signature,
        )
        phrasing = (
            OpenAIPhrasingAdapter(self.llm)
            if self.llm is not None and self.ai_mode in {"phrasing", "all"}
            else None
        )
        generated = render_outreach(template_context, phrasing=phrasing)
        validated_strategy = phrasing.last_strategy if phrasing and phrasing.last_strategy else strategy
        try:
            OutreachPolicyValidator().validate(
                strategy=validated_strategy,
                generation=generated,
            )
        except ValidationError:
            if phrasing is None:
                raise
            generated = render_outreach(template_context)
            validated_strategy = strategy
            OutreachPolicyValidator().validate(strategy=strategy, generation=generated)
        strategy = validated_strategy
        alternatives = self._alternatives(
            playbooks=playbooks,
            playbook_match=playbook_match,
            stable_key=stable_key,
            trade_key=business.category_key or "default",
            business_name=business.display_name,
            signature=signature,
        )
        return OutreachPackageContent(
            observation=observation,
            evidence=evidence,
            message=generated.message,
            call=generated.call if business.phone else None,
            form=generated.form if contact_url else None,
            email=generated.email if email else None,
            strategy=strategy,
            alternatives=alternatives,
            reply_paths=strategy.reply_paths,
        )

    def _alternatives(
        self,
        *,
        playbooks: PlaybookRepository,
        playbook_match,
        stable_key: str,
        trade_key: str,
        business_name: str,
        signature: str,
    ) -> list[DraftAlternative]:
        alternatives: list[DraftAlternative] = []
        for offset, label in ((1, "Direct"), (2, "Consultative")):
            strategy = playbooks.strategy_for(
                playbook_match,
                stable_key=stable_key,
                trade_key=trade_key,
                variant_offset=offset,
            )
            generated = render_outreach(
                OutreachTemplateContext(
                    business_name=business_name,
                    strategy=strategy,
                    signature=signature,
                )
            )
            OutreachPolicyValidator().validate(strategy=strategy, generation=generated)
            variant_id = f"{strategy.experiment_id}:{strategy.selected_variant}"
            alternatives.extend(
                [
                    DraftAlternative(id=variant_id, label=label, channel="message", body=generated.message.body),
                    DraftAlternative(id=variant_id, label=label, channel="form", body=generated.form.body),
                    DraftAlternative(id=variant_id, label=label, channel="email", subject=generated.email.subject, body=generated.email.body),
                ]
            )
        return alternatives

    def update(self, package_id: str, data: OutreachPackageUpdate) -> OutreachPackageRead:
        row = self._owned(package_id)
        result, _, _, business, _ = self._context(row.audience_result_id)
        original = OutreachPackageContent.model_validate(row.content)
        if (
            data.content.observation != original.observation
            or data.content.evidence != original.evidence
            or data.content.strategy != original.strategy
            or data.content.alternatives != original.alternatives
            or data.content.reply_paths != original.reply_paths
        ):
            raise ValidationError("Verified outreach evidence cannot be edited in a draft update.")
        if data.content.call and data.content.call.selected_branch:
            branch_keys = {branch.key for branch in data.content.call.branches}
            if data.content.call.selected_branch not in branch_keys:
                raise ValidationError(
                    "Selected call response is not part of this outreach playbook."
                )
        row.content = data.content.model_dump()
        self.session.commit()
        self.session.refresh(row)
        return self._read(row, business, result)

    def generate_ai_suggestion(
        self,
        package_id: str,
        data: OutreachAISuggestionRequest,
    ) -> DraftAlternative:
        row = self._owned(package_id)
        content = OutreachPackageContent.model_validate(row.content)
        if content.strategy is None or self.llm is None:
            raise ConfigurationError(
                "AI outreach suggestion is unavailable",
                {"user_message": "OpenAI suggestions are not configured for this account."},
            )

        result, _, product, business, workspace = self._context(row.audience_result_id)
        signature = (
            (workspace.sender_legal_name if workspace else None)
            or (workspace.sender_contact if workspace else None)
            or product.product_name
        )
        adapter = OpenAIPhrasingAdapter(self.llm)
        generated = render_outreach(
            OutreachTemplateContext(
                business_name=business.display_name,
                strategy=content.strategy,
                signature=signature,
            ),
            phrasing=adapter,
        )
        if adapter.last_strategy is None:
            raise ConfigurationError(
                "AI outreach suggestion could not be generated",
                {"user_message": "OpenAI could not generate a grounded suggestion. Try again."},
            )
        OutreachPolicyValidator().validate(
            strategy=adapter.last_strategy,
            generation=generated,
        )

        suggestion_id = f"openai:{data.channel}:{new_id('variant')}"
        if data.channel == "message":
            return DraftAlternative(
                id=suggestion_id,
                label="AI suggestion",
                channel=data.channel,
                body=generated.message.body,
            )
        if data.channel == "form":
            return DraftAlternative(
                id=suggestion_id,
                label="AI suggestion",
                channel=data.channel,
                body=generated.form.body,
            )
        return DraftAlternative(
            id=suggestion_id,
            label="AI suggestion",
            channel=data.channel,
            subject=generated.email.subject,
            body=generated.email.body,
        )

    def classify_response(
        self,
        package_id: str,
        data: OutreachResponseClassifyRequest,
    ) -> OutreachResponseClassification:
        row = self._owned(package_id)
        content = OutreachPackageContent.model_validate(row.content)
        result = ResponseClassifier(
            llm=self.llm,
            use_ai=self.ai_mode in {"classification", "all"},
        ).classify(
            response_text=data.response_text,
            channel=data.channel,
            paths=content.reply_paths,
        )
        self.record_event(
            package_id,
            OutreachEventCreate(
                channel=data.channel,
                event_type="response_classified",
                variant_id=content.strategy.selected_variant if content.strategy else None,
                metadata={
                    "category": result.category,
                    "confidence": result.confidence,
                    "source": result.source,
                },
            ),
        )
        return result

    def record_event(
        self,
        package_id: str,
        data: OutreachEventCreate,
    ) -> OutreachEventRead:
        self._owned(package_id)
        return OutreachEventRepository(
            self.session,
            workspace_id=self.workspace_id,
        ).record(package_id, data)

    def analytics(self) -> OutreachAnalyticsRead:
        return OutreachEventRepository(
            self.session,
            workspace_id=self.workspace_id,
        ).analytics()

    def prepare_message(self, package_id: str) -> MessageRead:
        """Snapshot the package email into the approval and sending workflow."""
        package = self._owned(package_id)
        messages = MessageRepository(self.session, workspace_id=self.workspace_id)
        existing = messages.find_for_outreach_package(package.id)
        if existing is not None:
            return MessageRead.model_validate(existing)

        result, audience, _, _, _ = self._context(package.audience_result_id)
        lead = AudienceOutreachService(
            self.session,
            workspace_id=self.workspace_id,
        ).promote(result.id)
        run = self.session.get(AudienceRunModel, result.run_id)
        if run is None or run.outreach_campaign_id is None:
            raise WorkflowBoundaryError(
                "The audience result could not be attached to an outreach campaign.",
                {"package_id": package_id},
            )

        content = OutreachPackageContent.model_validate(package.content)
        if content.email is None:
            raise WorkflowBoundaryError(
                "This outreach package does not contain an email draft.",
                {"package_id": package_id},
            )
        message = messages.create_draft(
            run.outreach_campaign_id,
            audience.product_id,
            lead.id,
            OutreachDraft(
                channel=OutreachChannel.EMAIL,
                subject=content.email.subject,
                body=content.email.body,
                personalization_notes=[item.statement for item in content.evidence],
                approach_tag="outreach_package",
            ),
            outreach_package_id=package.id,
        )
        return MessageRead.model_validate(message)

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


def _should_refresh_template(row: OutreachPackageModel) -> bool:
    if row.provider != "template" or row.prompt_version >= TEMPLATE_VERSION:
        return False
    content = row.content if isinstance(row.content, dict) else {}
    message = content.get("message") if isinstance(content.get("message"), dict) else {}
    body = str(message.get("body") or "").lower()
    return any(
        marker in body
        for marker in (
            " on businesses in ",
            "that help local service businesses generate more qualified inquiries and quote requests",
        )
    )


def _needs_strategy_upgrade(row: OutreachPackageModel) -> bool:
    if row.provider != "template":
        return False
    content = row.content if isinstance(row.content, dict) else {}
    strategy = content.get("strategy") if isinstance(content.get("strategy"), dict) else {}
    return (
        row.prompt_version < TEMPLATE_VERSION
        or "customer_consequence" not in strategy
        or "reply_paths" not in content
        or "alternatives" not in content
    )


def _upgrade_content(
    row: OutreachPackageModel,
    fresh: OutreachPackageContent,
) -> OutreachPackageContent:
    if _should_refresh_template(row) or _looks_like_generated_copy(row.content):
        return fresh
    return _merge_legacy_draft(row.content, fresh)


def _looks_like_generated_copy(value: object) -> bool:
    if not isinstance(value, dict):
        return True
    strategy = value.get("strategy") if isinstance(value.get("strategy"), dict) else {}
    message = value.get("message") if isinstance(value.get("message"), dict) else {}
    body = str(message.get("body") or "")
    observation = str(strategy.get("observation") or "")
    positioning = str(strategy.get("seller_positioning") or "")
    next_step = str(strategy.get("next_step") or "")
    return bool(
        body
        and observation
        and positioning
        and next_step
        and observation in body
        and positioning in body
        and next_step in body
    )


def _merge_legacy_draft(
    legacy_data: dict[str, Any],
    fresh: OutreachPackageContent,
) -> OutreachPackageContent:
    merged = fresh.model_copy(deep=True)
    if isinstance(legacy_data.get("message"), dict):
        merged.message = WrittenDraft.model_validate(legacy_data["message"])
    if isinstance(legacy_data.get("call"), dict) and merged.call:
        legacy_call = CallDraft.model_validate(legacy_data["call"])
        merged.call.opener = legacy_call.opener
        merged.call.permission = legacy_call.permission
        merged.call.observation = legacy_call.observation
        merged.call.discovery_question = legacy_call.discovery_question
        merged.call.ask = legacy_call.ask
    if isinstance(legacy_data.get("form"), dict) and merged.form:
        merged.form = WrittenDraft.model_validate(legacy_data["form"])
    if isinstance(legacy_data.get("email"), dict) and merged.email:
        merged.email = EmailDraft.model_validate(legacy_data["email"])
    return merged
