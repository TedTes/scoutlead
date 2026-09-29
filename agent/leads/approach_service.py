from datetime import datetime, timezone

from sqlalchemy.orm import Session

from agents.llm import LLMClient
from leads.policy import best_contact_channel, normalize_agent_fit_status
from leads.repository import LeadRepository
from leads.schemas import (
    AgentFitStatus,
    ApproachCopy,
    BestChannel,
    LeadApproach,
    LeadRead,
)
from products.repository import ProductRepository
from products.schemas import ProductRead
from prompts.approach import approach_prompt
from shared.errors import ConflictError
from shared.utils import utcnow


class LeadApproachService:
    def __init__(
        self,
        *,
        session: Session,
        llm: LLMClient,
        workspace_id: str | None,
    ) -> None:
        self.session = session
        self.llm = llm
        self.leads = LeadRepository(session, workspace_id=workspace_id)
        self.products = ProductRepository(session, workspace_id=workspace_id)

    def generate(self, lead_id: str, *, force: bool = False) -> LeadRead:
        model = self.leads.get(lead_id)
        lead = LeadRead.model_validate(model)
        product = ProductRead.model_validate(self.products.get(lead.product_id))
        if (
            lead.approach
            and not force
            and _aware(lead.approach.offer_updated_at) >= _aware(product.updated_at)
        ):
            return lead
        if not lead.qualification or normalize_agent_fit_status(lead.qualification) not in {
            AgentFitStatus.GOOD_FIT,
            AgentFitStatus.MAYBE,
        }:
            raise ConflictError("approach requires a good-fit or possible-fit contact")
        channel, reason = best_contact_channel(lead)
        if channel == BestChannel.NONE:
            raise ConflictError("approach requires a reachable contact channel")
        copy = self.llm.generate_object(
            task="lead_approach",
            system="Write an evidence-grounded sales approach without inventing claims.",
            prompt=approach_prompt(product, lead, channel=channel),
            response_model=ApproachCopy,
            context={
                "product": product.model_dump(mode="json"),
                "lead": lead.model_dump(mode="json"),
                "best_channel": channel.value,
            },
        )
        approach = LeadApproach(
            **copy.model_dump(mode="python"),
            best_channel=channel,
            channel_reason=reason,
            generated_at=utcnow(),
            offer_updated_at=product.updated_at,
        )
        model.approach = approach.model_dump(mode="json")
        self.session.commit()
        self.session.refresh(model)
        return LeadRead.model_validate(model)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
