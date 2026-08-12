from conversations.schemas import (
    FollowUpAction,
    ResponseClassification,
    ResponseIntent,
)
from leads.schemas import LeadRead
from products.schemas import ProductRead


def response_prompt(product: ProductRead, lead: LeadRead, body: str) -> str:
    return "\n".join(
        [
            f"Product: {product.product_name}",
            f"Lead: {lead.company_name}",
            f"Inbound response: {body}",
        ]
    )


def fallback_response_classification(body: str) -> ResponseClassification:
    normalized = body.lower()
    if any(token in normalized for token in ["book", "schedule", "calendar", "call", "interview"]):
        return ResponseClassification(
            intent=ResponseIntent.INTERVIEW_REQUEST,
            confidence=82,
            rationale="Response contains scheduling or interview language.",
            follow_up_action=FollowUpAction.SCHEDULE_INTERVIEW,
            suggested_reply="Share availability and confirm the discovery interview.",
        )
    if any(token in normalized for token in ["trial", "demo", "try", "pilot", "access"]):
        return ResponseClassification(
            intent=ResponseIntent.PRODUCT_TRIAL_INTEREST,
            confidence=78,
            rationale="Response asks about trying or seeing the product.",
            follow_up_action=FollowUpAction.SEND_TRIAL_INFO,
        )
    if any(token in normalized for token in ["not interested", "unsubscribe", "no thanks", "remove me"]):
        return ResponseClassification(
            intent=ResponseIntent.NOT_INTERESTED,
            confidence=88,
            rationale="Response declines further outreach.",
            follow_up_action=FollowUpAction.CLOSE,
        )
    if "?" in normalized or any(token in normalized for token in ["how", "what", "why", "price", "cost"]):
        return ResponseClassification(
            intent=ResponseIntent.QUESTION,
            confidence=72,
            rationale="Response appears to ask a question.",
            follow_up_action=FollowUpAction.REPLY,
        )
    if any(token in normalized for token in ["interested", "sounds good", "tell me more", "yes"]):
        return ResponseClassification(
            intent=ResponseIntent.INTERESTED,
            confidence=70,
            rationale="Response expresses positive interest.",
            follow_up_action=FollowUpAction.REPLY,
        )
    return ResponseClassification(
        intent=ResponseIntent.UNKNOWN,
        confidence=45,
        rationale="No strong response intent detected.",
        follow_up_action=FollowUpAction.MANUAL_REVIEW,
    )
