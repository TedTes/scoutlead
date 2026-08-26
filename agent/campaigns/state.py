from campaigns.schemas import CampaignStatus
from shared.errors import WorkflowBoundaryError


ALLOWED_CAMPAIGN_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.DRAFT: {CampaignStatus.DISCOVERING, CampaignStatus.PAUSED, CampaignStatus.FAILED},
    CampaignStatus.DISCOVERING: {CampaignStatus.RESEARCHING, CampaignStatus.FAILED, CampaignStatus.PAUSED},
    CampaignStatus.RESEARCHING: {CampaignStatus.QUALIFYING, CampaignStatus.FAILED, CampaignStatus.PAUSED},
    CampaignStatus.QUALIFYING: {
        CampaignStatus.DRAFTING_OUTREACH,
        CampaignStatus.AWAITING_APPROVAL,
        CampaignStatus.COMPLETED,
        CampaignStatus.FAILED,
        CampaignStatus.PAUSED,
    },
    CampaignStatus.DRAFTING_OUTREACH: {
        CampaignStatus.AWAITING_APPROVAL,
        CampaignStatus.COMPLETED,
        CampaignStatus.FAILED,
        CampaignStatus.PAUSED,
    },
    CampaignStatus.AWAITING_APPROVAL: {
        CampaignStatus.SENDING,
        CampaignStatus.TRACKING,
        CampaignStatus.COMPLETED,
        CampaignStatus.PAUSED,
        CampaignStatus.FAILED,
    },
    CampaignStatus.SENDING: {CampaignStatus.TRACKING, CampaignStatus.FAILED, CampaignStatus.PAUSED},
    CampaignStatus.TRACKING: {CampaignStatus.COMPLETED, CampaignStatus.PAUSED, CampaignStatus.FAILED},
    CampaignStatus.PAUSED: {
        CampaignStatus.DISCOVERING,
        CampaignStatus.RESEARCHING,
        CampaignStatus.QUALIFYING,
        CampaignStatus.DRAFTING_OUTREACH,
        CampaignStatus.AWAITING_APPROVAL,
        CampaignStatus.TRACKING,
        CampaignStatus.FAILED,
    },
    CampaignStatus.COMPLETED: set(),
    CampaignStatus.FAILED: set(),
}


def assert_campaign_transition(current: CampaignStatus, target: CampaignStatus) -> None:
    if current == target:
        return
    if target not in ALLOWED_CAMPAIGN_TRANSITIONS[current]:
        raise WorkflowBoundaryError(
            f"campaign cannot transition from {current.value} to {target.value}",
            {"current": current.value, "target": target.value},
        )
