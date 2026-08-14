export type Product = {
  id: string;
  product_name: string;
  product_description: string;
  target_customer: string;
  problem_being_solved: string;
  value_proposition: string;
  target_geography: string;
  validation_goal: string;
  qualification_criteria: QualificationCriterion[];
  preferred_discovery_sources: DiscoverySource[];
  outreach_objective: string;
  constraints: string[];
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type QualificationCriterion = {
  id?: string | null;
  label: string;
  description?: string | null;
  weight: number;
  required: boolean;
  evidence_required: boolean;
};

export type DiscoverySource = {
  type: "web_search" | "directory" | "seed" | "manual" | "api";
  value: string;
  limit?: number | null;
  notes?: string | null;
};

export type Campaign = {
  id: string;
  product_id: string;
  name?: string | null;
  status: string;
  stage: string;
  max_leads: number;
  channels: string[];
  discovery_seeds: LeadSeedInput[];
  goal_override?: string | null;
  failure_reason?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type CampaignCreateInput = {
  product_id: string;
  name: string;
  max_leads: number;
  channels: string[];
  discovery_seeds?: LeadSeedInput[];
  goal_override?: string | null;
};

export type LeadSeedInput = {
  company_name: string;
  website_url?: string | null;
  contact_email?: string | null;
  geography?: string | null;
  description?: string | null;
  source?: string | null;
  raw?: Record<string, unknown> | null;
};

export type Lead = {
  id: string;
  company_name: string;
  website_url?: string;
  contact_email?: string;
  geography?: string;
  description?: string;
  source: string;
  status: string;
  created_at: string;
  updated_at: string;
  research?: {
    summary: string;
    business_type?: string;
    geography?: string | null;
    website_url?: string | null;
    signals: string[];
    pain_indicators: string[];
    disqualifiers?: string[];
    sources?: string[];
    contact_email?: string;
    contact_name?: string;
    confidence: number;
  };
  qualification?: {
    qualified: boolean;
    score: number;
    rationale: string;
    recommended_next_step?: string;
    criteria?: Array<{
      criterion_id: string;
      label: string;
      score: number;
      evidence: string[];
      missing_evidence: string[];
    }>;
  };
};

export type Message = {
  id: string;
  campaign_id: string;
  lead_id: string;
  product_id: string;
  channel: string;
  subject?: string;
  body: string;
  personalization_notes: string[];
  approach_tag: string;
  status: string;
  approval?: Record<string, unknown> | null;
  sent_at?: string | null;
  provider_message_id?: string | null;
  failure_reason?: string | null;
  created_at: string;
  updated_at: string;
};

export type Conversation = {
  id: string;
  campaign_id: string;
  product_id: string;
  lead_id: string;
  status: string;
  events: Array<{
    id: string;
    direction: string;
    message_id?: string | null;
    body: string;
    created_at: string;
    classification?: {
      intent: string;
      confidence: number;
      rationale: string;
      follow_up_action: string;
      suggested_reply?: string | null;
    };
  }>;
  created_at: string;
  updated_at: string;
};

export type Metrics = {
  lead_count: number;
  researched_lead_count: number;
  qualified_lead_count: number;
  average_lead_score: number;
  pending_approval_count: number;
  sent_count: number;
  response_count: number;
  response_rate: number;
  interview_request_count: number;
  interview_rate: number;
  trial_interest_count: number;
  approach_performance: Array<{
    approach_tag: string;
    sent: number;
    replies: number;
    positive_replies: number;
    response_rate: number;
    positive_response_rate: number;
  }>;
};

export type CampaignSnapshot = {
  campaign?: Campaign;
  leads: Lead[];
  messages: Message[];
  conversations: Conversation[];
  metrics?: Metrics;
};

export type ApiHealth = {
  status: string;
  service: string;
};

export type CampaignRunSummary = {
  campaign: Campaign;
  discovered_lead_count: number;
  researched_lead_count: number;
  qualified_lead_count: number;
  drafted_message_count: number;
};

export type ConnectionStatus = {
  name: string;
  category: string;
  status: "connected" | "not_configured" | "degraded";
  detail: string;
};

export type ManualClassificationInput = {
  intent:
    | "interested"
    | "not_interested"
    | "question"
    | "interview_request"
    | "product_trial_interest"
    | "out_of_office"
    | "unknown";
  confidence: number;
  rationale: string;
  follow_up_action: "reply" | "schedule_interview" | "send_trial_info" | "close" | "wait" | "manual_review";
  suggested_reply?: string | null;
};
