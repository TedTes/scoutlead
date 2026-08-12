from messages.schemas import MessageStatus
from shared.errors import ConflictError, WorkflowBoundaryError


ALLOWED_MESSAGE_TRANSITIONS: dict[MessageStatus, set[MessageStatus]] = {
    MessageStatus.DRAFT: {MessageStatus.PENDING_APPROVAL, MessageStatus.CANCELLED},
    MessageStatus.PENDING_APPROVAL: {MessageStatus.APPROVED, MessageStatus.CANCELLED},
    MessageStatus.APPROVED: {MessageStatus.SENT, MessageStatus.FAILED, MessageStatus.CANCELLED},
    MessageStatus.SENT: {MessageStatus.REPLIED, MessageStatus.FAILED},
    MessageStatus.REPLIED: set(),
    MessageStatus.FAILED: {MessageStatus.APPROVED, MessageStatus.CANCELLED},
    MessageStatus.CANCELLED: set(),
}


def assert_message_transition(current: MessageStatus, target: MessageStatus) -> None:
    if current == target:
        return
    if target not in ALLOWED_MESSAGE_TRANSITIONS[current]:
        raise WorkflowBoundaryError(
            f"message cannot transition from {current.value} to {target.value}",
            {"current": current.value, "target": target.value},
        )


def assert_send_allowed(status: MessageStatus) -> None:
    if status != MessageStatus.APPROVED:
        raise ConflictError(
            "human approval is required before sending outbound messages",
            {"status": status.value},
        )
