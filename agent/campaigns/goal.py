from __future__ import annotations

from dataclasses import dataclass

from campaigns.schemas import CampaignGoalType


@dataclass(frozen=True)
class CampaignGoalPolicy:
    goal_type: CampaignGoalType
    outreach_prompt_key: str
    north_star_metric: str
    positive_response_intents: tuple[str, ...]


GOAL_POLICIES: dict[CampaignGoalType, CampaignGoalPolicy] = {
    CampaignGoalType.LEARN: CampaignGoalPolicy(
        goal_type=CampaignGoalType.LEARN,
        outreach_prompt_key="learn",
        north_star_metric="interview_rate",
        positive_response_intents=("interview_request", "question", "interested"),
    ),
    CampaignGoalType.SELL: CampaignGoalPolicy(
        goal_type=CampaignGoalType.SELL,
        outreach_prompt_key="sell",
        north_star_metric="positive_response_rate",
        positive_response_intents=("trial_interest", "interested", "interview_request"),
    ),
}


def goal_policy(goal_type: CampaignGoalType | str | None) -> CampaignGoalPolicy:
    try:
        value = CampaignGoalType(goal_type or CampaignGoalType.LEARN)
    except ValueError:
        value = CampaignGoalType.LEARN
    return GOAL_POLICIES[value]
