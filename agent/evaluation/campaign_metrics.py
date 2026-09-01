from campaigns.goal import goal_policy
from campaigns.schemas import CampaignGoalType
from conversations.schemas import ConversationRead, ResponseIntent
from evaluation.lead_quality import evaluate_lead_quality
from evaluation.outreach import evaluate_outreach_approaches
from evaluation.schemas import CampaignMetrics
from leads.policy import can_shortlist_lead, is_reachable_lead, is_verified_lead
from leads.schemas import LeadRead
from messages.schemas import MessageRead, MessageStatus


def calculate_campaign_metrics(
    *,
    leads: list[LeadRead],
    messages: list[MessageRead],
    conversations: list[ConversationRead],
    goal_type: CampaignGoalType | str = CampaignGoalType.LEARN,
) -> CampaignMetrics:
    policy = goal_policy(goal_type)
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
    response_rate = len(inbound_events) / len(sent) if sent else 0
    interview_rate = interview_count / len(sent) if sent else 0
    active_messages = [message for message in messages if message.status != MessageStatus.CANCELLED]
    approach_performance = evaluate_outreach_approaches(
        messages,
        conversations,
        positive_intents=policy.positive_response_intents,
    )
    positive_response_rate = (
        sum(item.positive_replies for item in approach_performance) / len(sent) if sent else 0
    )
    north_star_values = {
        "interview_rate": interview_rate,
        "positive_response_rate": positive_response_rate,
        "response_rate": response_rate,
    }
    return CampaignMetrics(
        goal_type=policy.goal_type.value,
        north_star_metric=policy.north_star_metric,
        north_star_value=north_star_values.get(policy.north_star_metric, 0),
        lead_count=len(leads),
        researched_lead_count=sum(1 for lead in leads if lead.research is not None),
        reachable_lead_count=sum(1 for lead in leads if is_reachable_lead(lead)),
        verified_lead_count=sum(1 for lead in leads if is_verified_lead(lead)),
        qualified_lead_count=sum(1 for lead in leads if lead.qualification and lead.qualification.qualified),
        good_fit_lead_count=sum(
            1
            for lead in leads
            if can_shortlist_lead(review_status=lead.review_status, qualification=lead.qualification)
        ),
        shortlisted_lead_count=sum(1 for lead in leads if lead.shortlisted_at),
        average_lead_score=round(sum(scores) / len(scores)) if scores else 0,
        drafted_message_count=sum(
            1
            for message in active_messages
            if message.status in {MessageStatus.DRAFT, MessageStatus.PENDING_APPROVAL, MessageStatus.APPROVED}
        ),
        pending_approval_count=sum(
            1 for message in messages if message.status == MessageStatus.PENDING_APPROVAL
        ),
        approved_message_count=sum(1 for message in active_messages if message.status == MessageStatus.APPROVED),
        sent_count=len(sent),
        response_count=len(inbound_events),
        response_rate=response_rate,
        interview_request_count=interview_count,
        interview_rate=interview_rate,
        trial_interest_count=trial_count,
        approach_performance=approach_performance,
    )
