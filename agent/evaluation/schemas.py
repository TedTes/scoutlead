from pydantic import BaseModel


class LeadQualityEvaluation(BaseModel):
    lead_id: str
    score: int
    fit: str
    reasons: list[str]


class OutreachApproachEvaluation(BaseModel):
    approach_tag: str
    sent: int
    replies: int
    positive_replies: int
    response_rate: float
    positive_response_rate: float


class CampaignMetrics(BaseModel):
    goal_type: str = "learn"
    north_star_metric: str = "interview_rate"
    north_star_value: float = 0
    lead_count: int
    researched_lead_count: int
    reachable_lead_count: int = 0
    verified_lead_count: int = 0
    qualified_lead_count: int
    good_fit_lead_count: int = 0
    shortlisted_lead_count: int = 0
    average_lead_score: int
    drafted_message_count: int = 0
    pending_approval_count: int
    approved_message_count: int = 0
    sent_count: int
    response_count: int
    response_rate: float
    interview_request_count: int
    interview_rate: float
    trial_interest_count: int
    approach_performance: list[OutreachApproachEvaluation]
