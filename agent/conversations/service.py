from sqlalchemy.orm import Session

from agents.llm import LLMClient
from conversations.repository import ConversationRepository
from conversations.schemas import ConversationRead, ManualClassificationCreate, ResponseClassification
from leads.repository import LeadRepository
from memory.repository import MemoryRepository
from messages.repository import MessageRepository
from products.repository import ProductRepository
from products.schemas import ProductRead
from workflows.response import ResponseWorkflow


class ConversationService:
    def __init__(
        self,
        *,
        session: Session,
        llm: LLMClient,
        workspace_id: str | None = None,
    ) -> None:
        self.products = ProductRepository(session, workspace_id=workspace_id)
        self.leads = LeadRepository(session, workspace_id=workspace_id)
        self.messages = MessageRepository(session, workspace_id=workspace_id)
        self.conversations = ConversationRepository(session, workspace_id=workspace_id)
        self.memory = MemoryRepository(session)
        self.llm = llm

    def list_by_campaign(self, campaign_id: str) -> list[ConversationRead]:
        return [
            ConversationRead.model_validate(model)
            for model in self.conversations.list_by_campaign(campaign_id)
        ]

    def classify_response(self, conversation_id: str, body: str) -> ConversationRead:
        conversation = self.conversations.get(conversation_id)
        product = ProductRead.model_validate(self.products.get(conversation.product_id))
        return ResponseWorkflow(
            leads=self.leads,
            messages=self.messages,
            conversations=self.conversations,
            memory=self.memory,
            llm=self.llm,
        ).classify_inbound(product=product, conversation_id=conversation_id, body=body)

    def manually_classify(
        self, conversation_id: str, classification: ManualClassificationCreate
    ) -> ConversationRead:
        updated = self.conversations.add_manual_classification(
            conversation_id,
            ResponseClassification(
                intent=classification.intent,
                confidence=classification.confidence,
                rationale=classification.rationale,
                follow_up_action=classification.follow_up_action,
                suggested_reply=classification.suggested_reply,
            ),
        )
        return ConversationRead.model_validate(updated)
