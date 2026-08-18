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
  source_url?: string | null;
  source_fingerprint?: string | null;
  source_last_checked_at?: string | null;
  source_evidence?: Record<string, unknown> | null;
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type ProductSourceInput = {
  source: string;
  context?: string | null;
  target_geography?: string;
};

export type ProductSourceEvidence = {
  product_name_candidates: string[];
  headline?: string | null;
  claims: string[];
  target_customer_clues: string[];
  problem_clues: string[];
  value_clues: string[];
  source_snippets: string[];
  confidence: number;
  missing_info: string[];
  rationale: string;
};

export type ProductInference = {
  source: string;
  context?: string | null;
  ready_to_save: boolean;
  confidence: number;
  missing_info: string[];
  evidence: ProductSourceEvidence;
  product: Omit<Product, "id" | "archived_at" | "created_at" | "updated_at">;
  existing_product?: Product | null;
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

export type AgentRunStatus = "queued" | "running" | "waiting" | "completed" | "failed" | "cancelled";

export type AgentStepStatus = "pending" | "running" | "completed" | "failed" | "skipped";

export type ToolCallStatus = "running" | "completed" | "failed";

export type AgentStep = {
  id: string;
  run_id: string;
  campaign_id: string;
  phase: string;
  status: AgentStepStatus;
  sequence: number;
  objective: string;
  input_snapshot: Record<string, unknown>;
  output_snapshot?: Record<string, unknown> | null;
  observation?: Record<string, unknown> | null;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type ToolCall = {
  id: string;
  run_id: string;
  step_id?: string | null;
  campaign_id: string;
  tool_name: string;
  status: ToolCallStatus;
  reason?: string | null;
  args: Record<string, unknown>;
  observation?: Record<string, unknown> | unknown[] | string | null;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentRun = {
  id: string;
  campaign_id: string;
  product_id: string;
  kind: "campaign";
  objective: string;
  status: AgentRunStatus;
  current_phase?: string | null;
  context_snapshot: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  error?: string | null;
  max_tool_calls: number;
  max_llm_calls: number;
  max_leads: number;
  tool_call_count: number;
  llm_call_count: number;
  started_at?: string | null;
  heartbeat_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentRunDetail = AgentRun & {
  steps: AgentStep[];
  tool_calls: ToolCall[];
};

export type CampaignPreflightCheck = {
  name: string;
  status: string;
  detail: string;
  required: boolean;
};

export type CampaignPreflight = {
  campaign_id: string;
  ready: boolean;
  checks: CampaignPreflightCheck[];
};

export type CampaignSnapshot = {
  campaign?: Campaign;
  leads: Lead[];
  messages: Message[];
  conversations: Conversation[];
  metrics?: Metrics;
  preflight?: CampaignPreflight;
  agentRuns: AgentRun[];
  latestAgentRun?: AgentRunDetail;
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
