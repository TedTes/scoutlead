from sqlalchemy.orm import Session

from job_queue.service import QueueService
from source_items.repository import SourceItemRepository
from source_items.schemas import (
    SourceItemDecisionCreate,
    SourceItemDecisionValue,
    SourceItemReview,
    SourceItemReviewAction,
    SourceItemStage,
    SourceItemState,
)


class SourceItemReviewService:
    def __init__(self, session: Session) -> None:
        self.items = SourceItemRepository(session)
        self.queue = QueueService(session)

    def review(self, source_item_id: str, review: SourceItemReview, *, actor_id: str | None):
        item = self.items.get(source_item_id)
        decision, state, stage = _review_transition(
            review.action,
            has_business=bool(item.business_id),
        )
        reason = review.reason or _default_reason(review.action)
        self.items.add_decision(
            item.id,
            SourceItemDecisionCreate(
                stage=stage,
                decision=decision,
                reason=reason,
                actor_type="user",
                actor_id=actor_id,
                details={"review_action": review.action.value},
            ),
            next_state=state,
        )
        if review.action == SourceItemReviewAction.ACCEPT and not item.business_id:
            self.queue.enqueue_business_identity_resolve(
                source_item_id=item.id,
                segment_id=item.segment_id,
            )
        elif (
            review.action in {SourceItemReviewAction.ACCEPT, SourceItemReviewAction.REAUDIT}
            and item.business_id
        ):
            self.queue.enqueue_business_opportunity_audit(
                source_item_id=item.id,
                segment_id=item.segment_id,
                business_id=item.business_id,
            )
        return self.items.get(item.id)


def _review_transition(
    action: SourceItemReviewAction,
    *,
    has_business: bool,
) -> tuple[SourceItemDecisionValue, SourceItemState, SourceItemStage]:
    if action == SourceItemReviewAction.ACCEPT:
        return (
            SourceItemDecisionValue.ACCEPTED,
            SourceItemState.AUDIT_PENDING if has_business else SourceItemState.RELEVANT,
            SourceItemStage.RELEVANCE,
        )
    if action == SourceItemReviewAction.REJECT:
        return (
            SourceItemDecisionValue.REJECTED,
            SourceItemState.REJECTED,
            SourceItemStage.RELEVANCE,
        )
    if action == SourceItemReviewAction.DUPLICATE:
        return (
            SourceItemDecisionValue.DUPLICATE,
            SourceItemState.EXCLUDED,
            SourceItemStage.IDENTITY,
        )
    return (
        SourceItemDecisionValue.ACCEPTED,
        SourceItemState.AUDIT_PENDING if has_business else SourceItemState.NEEDS_REVIEW,
        SourceItemStage.OPPORTUNITY,
    )


def _default_reason(action: SourceItemReviewAction) -> str:
    return {
        SourceItemReviewAction.ACCEPT: "Accepted by reviewer.",
        SourceItemReviewAction.REJECT: "Rejected by reviewer.",
        SourceItemReviewAction.DUPLICATE: "Marked as a duplicate by reviewer.",
        SourceItemReviewAction.REAUDIT: "Reviewer requested a new opportunity audit.",
    }[action]
