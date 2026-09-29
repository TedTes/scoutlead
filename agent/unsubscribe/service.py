from sqlalchemy.orm import Session

from db.models import LeadModel, ProductModel
from leads.schemas import ContactPolicyStatus, SuppressionScope
from outcomes.schemas import LeadOutcome, LeadOutcomeCreate, OutcomeChannel, OutcomeSource
from outcomes.service import OutcomeService
from shared.errors import NotFoundError, ValidationError
from suppressions.repository import ContactSuppressionRepository, normalize_email
from unsubscribe.tokens import UnsubscribeClaims, verify_unsubscribe_token


class UnsubscribeService:
    def __init__(self, session: Session, *, signing_secret: str | None) -> None:
        self.session = session
        self.signing_secret = signing_secret or ""

    def claims(self, token: str) -> UnsubscribeClaims:
        claims = verify_unsubscribe_token(token, self.signing_secret)
        lead = self._lead(claims)
        if normalize_email(lead.contact_email) != normalize_email(str(claims.email)):
            raise ValidationError("unsubscribe token does not match the current contact")
        return claims

    def unsubscribe(self, token: str) -> LeadModel:
        claims = self.claims(token)
        lead = self._lead(claims)
        updated = ContactSuppressionRepository(self.session).set_lead_policy(
            lead,
            status=ContactPolicyStatus.UNSUBSCRIBED,
            reason="Contact used the unsubscribe link.",
            scope=SuppressionScope.WORKSPACE,
            source="unsubscribe_link",
        )
        OutcomeService(
            self.session,
            workspace_id=claims.workspace_id,
        ).record(
            lead.id,
            LeadOutcomeCreate(
                outcome=LeadOutcome.UNSUBSCRIBED,
                channel=OutcomeChannel.EMAIL,
                source=OutcomeSource.UNSUBSCRIBE_LINK,
            ),
        )
        return updated

    def _lead(self, claims: UnsubscribeClaims) -> LeadModel:
        lead = self.session.get(LeadModel, claims.lead_id)
        if lead is None:
            raise NotFoundError("unsubscribe contact not found")
        product = self.session.get(ProductModel, lead.product_id)
        product_workspace_id = product.workspace_id if product else None
        if product_workspace_id != claims.workspace_id:
            raise ValidationError("unsubscribe token does not match the workspace")
        return lead
