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
    lead_count: int
    researched_lead_count: int
    qualified_lead_count: int
    average_lead_score: int
    pending_approval_count: int
    sent_count: int
    response_count: int
    response_rate: float
    interview_request_count: int
    interview_rate: float
    trial_interest_count: int
    approach_performance: list[OutreachApproachEvaluation]
