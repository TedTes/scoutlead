from agents.llm import LLMClient
from conversations.repository import ConversationRepository
from conversations.schemas import ConversationRead, ResponseClassification
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadStatus
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from messages.repository import MessageRepository
from messages.schemas import MessageStatus
from products.schemas import ProductRead
from prompts.response import fallback_response_classification, response_prompt


class ResponseWorkflow:
    def __init__(
        self,
        *,
        leads: LeadRepository,
        messages: MessageRepository,
        conversations: ConversationRepository,
        memory: MemoryRepository,
        llm: LLMClient,
    ) -> None:
        self.leads = leads
        self.messages = messages
        self.conversations = conversations
        self.memory = memory
        self.llm = llm

    def classify_inbound(
        self, *, product: ProductRead, conversation_id: str, body: str
    ) -> ConversationRead:
        conversation = self.conversations.get(conversation_id)
        lead = LeadRead.model_validate(self.leads.get(conversation.lead_id))
        fallback = fallback_response_classification(body)
        classification = self.llm.generate_object(
            task="response_classification",
            system="Classify an inbound response into the allowed response labels.",
            prompt=response_prompt(product, lead, body),
            response_model=ResponseClassification,
            context={
                "product": product.model_dump(mode="json"),
                "lead": lead.model_dump(mode="json"),
                "body": body,
            },
            fallback=fallback,
        )
        updated = self.conversations.add_inbound_event(conversation_id, body, classification)
        self.leads.update_status(lead.id, LeadStatus.RESPONDED)
        for message in self.messages.list_by_lead(lead.id):
            if message.status == MessageStatus.SENT.value:
                self.messages.set_status(message.id, MessageStatus.REPLIED)
        self.memory.create_observation(
            CampaignMemoryCreate(
                product_id=product.id,
                campaign_id=conversation.campaign_id,
                type=ObservationType.RESPONSE,
                content=f"{lead.company_name} response classified as {classification.intent.value}: "
                f"{classification.rationale}",
                tags=["response", classification.intent.value],
            )
        )
        return ConversationRead.model_validate(updated)
