from sqlalchemy.orm import Session

from leads.repository import LeadRepository
from messages.repository import MessageRepository


class DatabaseTool:
    name = "database"

    def __init__(self, session: Session) -> None:
        self.session = session

    def execute(self, args: dict) -> dict:
        operation = args.get("operation")
        if operation == "campaign_snapshot":
            campaign_id = str(args["campaign_id"])
            leads = LeadRepository(self.session).list_by_campaign(campaign_id)
            messages = MessageRepository(self.session).list_by_campaign(campaign_id)
            return {
                "lead_count": len(leads),
                "message_count": len(messages),
                "qualified_lead_count": sum(1 for lead in leads if lead.status == "qualified"),
                "pending_approval_count": sum(
                    1 for message in messages if message.status == "pending_approval"
                ),
            }
        return {"error": f"unsupported database operation: {operation}"}
