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
  webhook_url?: string | null;
  webhook_enabled?: boolean;
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type ProductDescriptionInput = {
  product_name: string;
  description: string;
  target_geography?: string;
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

export type DiscoveryRun = {
  id: string;
  product_id: string;
  name?: string | null;
  goal_type: "learn" | "sell";
  icp_preset_id?: string | null;
  source_preset_id?: string | null;
  source_input?: string | null;
  source_inputs?: Record<string, unknown>;
  status: string;
  stage: string;
  max_leads: number;
  channels: string[];
  discovery_seeds: ResultSeedInput[];
  goal_override?: string | null;
  failure_reason?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type DiscoveryRunSource = {
  id: string;
  campaign_id: string;
  slot: "discovery" | "contact" | "verify" | "signal";
  provider_id: string;
  mode: "accumulate" | "first_good";
  input: Record<string, unknown>;
  config: Record<string, unknown>;
  priority: number;
  enabled: boolean;
  budget_limit?: number | null;
  created_at: string;
  updated_at: string;
};

export type DiscoveryRunCreateInput = {
  product_id: string;
  name: string;
  goal_type?: "learn" | "sell";
  icp_preset_id?: string | null;
  source_preset_id?: string | null;
  source_input?: string | null;
  source_inputs?: Record<string, unknown>;
  max_leads: number;
  channels: string[];
  discovery_seeds?: ResultSeedInput[];
  goal_override?: string | null;
};

export type SourceRequestSource = string;

export type SourceProvider = {
  id: string;
  label: string;
  configured: boolean;
  detail?: string | null;
};

export type GmailConnectionStatus = {
  product_id: string;
  provider: "gmail";
  connected: boolean;
  email_address?: string | null;
  scopes: string[];
  last_error?: string | null;
};

export type GmailAuthorizationUrl = {
  authorization_url: string;
};

export type SourceRequestInput = {
  product_id: string;
  source: SourceRequestSource;
  name?: string;
  prompt: string;
  max_results: number;
  run_immediately?: boolean;
};

export type SourceRequestRun = {
  plan: {
    source: SourceRequestSource;
    action: "list_contacts";
    query: string;
    max_results: number;
    source_preset_id: string;
    explanation: string;
  };
  run: DiscoveryRun;
  summary?: DiscoveryRunSummary | null;
};

export type ResultSeedInput = {
  company_name: string;
  website_url?: string | null;
  contact_email?: string | null;
  geography?: string | null;
  description?: string | null;
  source?: string | null;
  raw?: Record<string, unknown> | null;
};

export type LeadReviewStatus = "unreviewed" | "good_fit" | "maybe" | "not_fit";
export type AgentFitStatus = "good_fit" | "maybe" | "not_fit";
export type ContactVerificationStatus = "unverified" | "valid" | "risky" | "invalid" | "unknown";
export type ContactPolicyStatus = "allowed" | "suppressed" | "unsubscribed" | "bounced";
export type SuppressionScope = "product" | "global";

export type LeadUpdateInput = {
  review_status?: LeadReviewStatus;
  review_note?: string | null;
  shortlisted?: boolean;
};

export type LeadContactPolicyInput = {
  status: ContactPolicyStatus;
  reason?: string | null;
  scope?: SuppressionScope;
};

export type DiscoveryResult = {
  id: string;
  campaign_id: string;
  product_id: string;
  company_name: string;
  website_url?: string;
  contact_email?: string;
  geography?: string;
  description?: string;
  source: string;
  raw_sources?: Array<Record<string, unknown>>;
  status: string;
  review_status?: LeadReviewStatus;
  review_note?: string | null;
  reviewed_at?: string | null;
  shortlisted_at?: string | null;
  contact_policy_status?: ContactPolicyStatus;
  contact_policy_reason?: string | null;
  contact_policy_checked_at?: string | null;
  last_contacted_at?: string | null;
  verification_status?: ContactVerificationStatus;
  verification_provider?: string | null;
  verification_checked_at?: string | null;
  verification_reason?: string | null;
  verification_score?: number | null;
  verification_details?: Record<string, unknown> | null;
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
    fit_status?: AgentFitStatus | null;
    score: number;
    rationale: string;
    positive_signals?: string[];
    missing_evidence?: string[];
    risks?: string[];
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

export type DiscoveryCandidate = {
  id: string;
  campaign_id: string;
  product_id: string;
  lead_id?: string | null;
  query: string;
  title: string;
  url?: string | null;
  snippet?: string | null;
  geography?: string | null;
  contact_email?: string | null;
  source: string;
  raw: Record<string, unknown>;
  candidate_type:
    | "target_business"
    | "competitor"
    | "vendor"
    | "directory"
    | "content"
    | "salary"
    | "job"
    | "social"
    | "irrelevant"
    | "unknown";
  confidence: number;
  rejection_reason?: string | null;
  promoted_at?: string | null;
  created_at: string;
  updated_at: string;
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

export type WebhookDelivery = {
  id: string;
  product_id: string;
  campaign_id: string;
  event: string;
  url: string;
  status: "success" | "failed";
  request_payload: Record<string, unknown>;
  response_status?: number | null;
  response_body?: string | null;
  error?: string | null;
  created_at: string;
  updated_at: string;
};

export type Metrics = {
  goal_type: "learn" | "sell";
  north_star_metric: string;
  north_star_value: number;
  lead_count: number;
  researched_lead_count: number;
  reachable_lead_count: number;
  verified_lead_count: number;
  qualified_lead_count: number;
  good_fit_lead_count: number;
  shortlisted_lead_count: number;
  average_lead_score: number;
  drafted_message_count: number;
  pending_approval_count: number;
  approved_message_count: number;
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

export type DiscoveryTrace = {
  campaign_id: string;
  run_count: number;
  latest_run?: AgentRunDetail | null;
  runs: AgentRunDetail[];
};

export type DiscoveryPreflightCheck = {
  name: string;
  status: string;
  detail: string;
  required: boolean;
};

export type DiscoveryPreflight = {
  campaign_id: string;
  ready: boolean;
  checks: DiscoveryPreflightCheck[];
};

export type DiscoverySnapshot = {
  run?: DiscoveryRun;
  sourceConfigs: DiscoveryRunSource[];
  results: DiscoveryResult[];
  discoveryCandidates: DiscoveryCandidate[];
  messages: Message[];
  metrics?: Metrics;
  preflight?: DiscoveryPreflight;
  trace?: DiscoveryTrace;
  agentRuns: AgentRun[];
  latestAgentRun?: AgentRunDetail;
};

export type ApiHealth = {
  status: string;
  service: string;
};

export type DiscoveryRunSummary = {
  campaign: DiscoveryRun;
  discovered_lead_count: number;
  researched_lead_count: number;
  contacted_lead_count: number;
  verified_lead_count: number;
  signaled_lead_count: number;
  qualified_lead_count: number;
  drafted_message_count: number;
};
