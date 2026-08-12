from collections import defaultdict

from conversations.schemas import ConversationRead, ResponseIntent
from evaluation.schemas import OutreachApproachEvaluation
from messages.schemas import MessageRead, MessageStatus


def evaluate_outreach_approaches(
    messages: list[MessageRead], conversations: list[ConversationRead]
) -> list[OutreachApproachEvaluation]:
    by_tag: dict[str, dict[str, int]] = defaultdict(
        lambda: {"sent": 0, "replies": 0, "positive_replies": 0}
    )
    conversations_by_lead = {conversation.lead_id: conversation for conversation in conversations}

    for message in messages:
        bucket = by_tag[message.approach_tag]
        if message.status in {MessageStatus.SENT, MessageStatus.REPLIED}:
            bucket["sent"] += 1

        conversation = conversations_by_lead.get(message.lead_id)
        inbound = [
            event
            for event in (conversation.events if conversation else [])
            if event.direction == "inbound"
        ]
        if inbound:
            bucket["replies"] += 1
        if any(
            event.classification
            and event.classification.intent
            in {
                ResponseIntent.INTERESTED,
                ResponseIntent.INTERVIEW_REQUEST,
                ResponseIntent.PRODUCT_TRIAL_INTEREST,
            }
            for event in inbound
        ):
            bucket["positive_replies"] += 1

    return [
        OutreachApproachEvaluation(
            approach_tag=tag,
            sent=values["sent"],
            replies=values["replies"],
            positive_replies=values["positive_replies"],
            response_rate=values["replies"] / values["sent"] if values["sent"] else 0,
            positive_response_rate=(
                values["positive_replies"] / values["sent"] if values["sent"] else 0
            ),
        )
        for tag, values in by_tag.items()
    ]
