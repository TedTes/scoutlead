from conversations.schemas import ConversationRead, ResponseIntent
from evaluation.lead_quality import evaluate_lead_quality
from evaluation.outreach import evaluate_outreach_approaches
from evaluation.schemas import CampaignMetrics
from leads.schemas import LeadRead
from messages.schemas import MessageRead, MessageStatus


def calculate_campaign_metrics(
    *,
    leads: list[LeadRead],
    messages: list[MessageRead],
    conversations: list[ConversationRead],
) -> CampaignMetrics:
    scores = [evaluate_lead_quality(lead).score for lead in leads]
    sent = [message for message in messages if message.status in {MessageStatus.SENT, MessageStatus.REPLIED}]
    inbound_events = [
        event
        for conversation in conversations
        for event in conversation.events
        if event.direction == "inbound"
    ]
    interview_count = sum(
        1
        for event in inbound_events
        if event.classification and event.classification.intent == ResponseIntent.INTERVIEW_REQUEST
    )
    trial_count = sum(
        1
        for event in inbound_events
        if event.classification and event.classification.intent == ResponseIntent.PRODUCT_TRIAL_INTEREST
    )
    return CampaignMetrics(
        lead_count=len(leads),
        researched_lead_count=sum(1 for lead in leads if lead.research is not None),
        qualified_lead_count=sum(1 for lead in leads if lead.qualification and lead.qualification.qualified),
        average_lead_score=round(sum(scores) / len(scores)) if scores else 0,
        pending_approval_count=sum(
            1 for message in messages if message.status == MessageStatus.PENDING_APPROVAL
        ),
        sent_count=len(sent),
        response_count=len(inbound_events),
        response_rate=len(inbound_events) / len(sent) if sent else 0,
        interview_request_count=interview_count,
        interview_rate=interview_count / len(sent) if sent else 0,
        trial_interest_count=trial_count,
        approach_performance=evaluate_outreach_approaches(messages, conversations),
    )
