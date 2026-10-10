export type Product = {
  id: string;
  product_name: string;
  product_description?: string | null;
  target_customer: string;
  problem_being_solved?: string | null;
  value_proposition?: string | null;
  target_geography: string;
  validation_goal?: string | null;
  qualification_criteria: QualificationCriterion[];
  preferred_discovery_sources: DiscoverySource[];
  outreach_objective?: string | null;
  constraints: string[];
  offer_summary?: string | null;
  ideal_customer_signals: string[];
  exclusions: string[];
  typical_deal_value?: string | null;
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

export type ProductProfileInput = {
  product_name: string;
  offer_summary: string;
  target_customer: string;
  problem_being_solved: string;
  target_geography?: string;
  ideal_customer_signals: string[];
  exclusions: string[];
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
  territory_id?: string | null;
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
  workspace_id?: string | null;
  provider: "gmail";
  connected: boolean;
  email_address?: string | null;
  scopes: string[];
  last_error?: string | null;
};

export type GmailAuthorizationUrl = {
  authorization_url: string;
};

export type SenderProfile = {
  workspace_id: string;
  sender_legal_name?: string | null;
  sender_mailing_address?: string | null;
  sender_contact?: string | null;
  complete: boolean;
};

export type SourceRequestInput = {
  product_id: string;
  source: SourceRequestSource;
  name?: string;
  prompt: string;
  max_results: number;
  run_immediately?: boolean;
  business_category?: string;
  geography?: string;
  opportunity_type?: "any" | "missing_website" | "missing_or_unavailable_website" | "weak_or_missing_website";
  evidence_max_age_days?: number;
  apply_product_defaults?: boolean;
  intent_override?: SearchIntent;
};

export type SearchCriterionMode = "required" | "alternative" | "excluded";

export type SearchIntentCriterion = {
  id: string;
  description: string;
  mode: SearchCriterionMode;
  fact_key?: string | null;
  operator?: string | null;
  value?: string | number | boolean | string[] | null;
  evidence_requirement: string;
};

export type SearchIntent = {
  schema_version: number;
  business_category: string;
  location: string;
  country?: string;
  included_subcategories: string[];
  criteria: SearchIntentCriterion[];
  contact_requirements: string[];
  required_signals: string[];
  excluded_result_types: string[];
  search_query: string;
  search_url?: string;
  confidence: number;
  rationale: string;
};

export type SourceRequestRun = {
  plan: {
    source: SourceRequestSource;
    action: "list_contacts";
    query: string;
    max_results: number;
    source_preset_id: string;
    explanation: string;
    tasks?: Array<{
      provider_id: string;
      query: string;
      stage: number;
      priority: number;
      max_results: number;
      reason: string;
    }>;
  };
  run: DiscoveryRun;
  summary?: DiscoveryRunSummary | null;
  state: "ready" | "expanding";
  current_result_count: number;
  requested_result_count: number;
  contract_hash: string;
  interpreted_intent?: SearchIntent | null;
  unsupported_criteria: string[];
  unresolved_criteria: string[];
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
export type SuppressionScope = "product" | "workspace" | "global";

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
  territory_id?: string | null;
  product_id: string;
  business_id?: string | null;
  outreach_lead_id?: string | null;
  contact_id?: string | null;
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
  latest_outcome?: string | null;
  latest_outcome_at?: string | null;
  approach?: {
    best_channel: "email" | "phone" | "contact_form" | "visit" | "none";
    channel_reason: string;
    opener?: string | null;
    talk_track?: string[];
    evidence_refs?: string[];
    generated_at?: string | null;
  } | null;
  outcome_adjustment?: number;
  rank_score?: number | null;
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
    score_breakdown?: {
      fit_score: number;
      reachability_score: number;
      source_quality_score: number;
      scoring_notes?: string[];
    } | null;
    rationale: string;
    positive_signals?: string[];
    signal_tags?: string[];
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

export type Territory = {
  id: string;
  workspace_id: string;
  product_id: string;
  niche_id: string;
  market_key: string;
  city: string;
  latitude?: number | null;
  longitude?: number | null;
  radius_km: number;
  trade_keys: ProfileTrade[];
  customer_kind: ProfileCustomerKind;
  signal_keys: string[];
  exclusion_keys: string[];
  label: string;
  status: "active" | "paused" | "archived";
  cadence: "weekly";
  refill_policy: "manual" | "when_depleted" | "weekly" | "biweekly" | "monthly";
  criteria_version: number;
  batch_size: number;
  min_fit: "good_fit" | "maybe";
  search_prompt?: string | null;
  search_contract: Record<string, unknown>;
  evidence_max_age_days: number;
  criteria_hash: string;
  next_run_at?: string | null;
  last_run_at?: string | null;
  last_delivery_count: number;
  unviewed_delivery_count: number;
  positive_outcome_rate: number;
  created_at: string;
  updated_at: string;
};

export type ProfileTrade = "painters" | "hvac" | "roofers" | "plumbers" | "electricians";
export type ProfileCustomerKind = "residential" | "commercial";
export type ProfileSignal = "website_unavailable" | "no_quote_flow" | "no_contact_form" | "reviews_under_15";
export type ProfileExclusion = "closed" | "chains" | "franchises" | "directories" | "agencies";

export type ProfileOptions = {
  business_types: Array<{
    key: ProfileTrade;
    label: string;
  }>;
};

export type ProfileFactChange = {
  id: string;
  business_id: string;
  business_name: string;
  fact_key: string;
  signal_key?: string | null;
  kind: "entered" | "exited" | "updated";
  previous_value?: string | number | boolean | null;
  current_value: string | number | boolean;
  previous_confidence?: number | null;
  current_confidence: number;
  changed_at: string;
};

export type ProfileCreateInput = {
  product_id: string;
  name?: string;
  trades: ProfileTrade[];
  customer_kind: ProfileCustomerKind;
  market: {
    city: string;
    radius_km: 10 | 25 | 50;
  };
  signals: ProfileSignal[];
  exclude: ProfileExclusion[];
  limit: 15 | 25 | 40;
  refill_policy: Territory["refill_policy"];
  exclude_already_delivered: true;
};

export type QueueJob = {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  status: "queued" | "running" | "completed" | "failed";
  attempts: number;
  max_attempts: number;
  run_after: string;
  last_error?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type ProfileQueued = {
  profile: Territory;
  job: QueueJob;
};

export type ProfileBatch = {
  profile: Territory;
  delivery?: TerritoryDelivery | null;
  audience_run_id?: string | null;
  outreach_campaign_id?: string | null;
  leads: DiscoveryResult[];
  state: "setup" | "scoring" | "retrying" | "ready" | "empty" | "partial" | "failed";
  requested_count: number;
  result_count: number;
  remaining_count: number;
  failure_class?: "rate_limit" | "quota" | "other" | null;
  retry_at?: string | null;
};

export type TerritoryResolution = {
  product_id: string;
  request: string;
  niche_id?: string | null;
  niche_slug: string;
  niche_label: string;
  niche_category: string;
  market_key: string;
  market_label: string;
  confidence: number;
  existing_niche: boolean;
  requires_confirmation: boolean;
};

export type TerritoryDelivery = {
  id: string;
  territory_id: string;
  campaign_id: string;
  scheduled_for?: string | null;
  started_at?: string | null;
  delivered_at?: string | null;
  viewed_at?: string | null;
  new_contact_count: number;
  status: "scheduled" | "running" | "ready" | "empty" | "partial" | "failed";
  failure_reason?: string | null;
};

export type TerritoryWeekMetrics = {
  week_start: string;
  delivered: number;
  contacted: number;
  replied: number;
  positive_reply_rate: number;
  meetings: number;
  won: number;
  not_a_fit_rate: number;
  data_quality_issue_rate: number;
  outcome_coverage: number;
};

export type TerritoryMetrics = {
  territory_id: string;
  weeks: number;
  totals: TerritoryWeekMetrics;
  by_week: TerritoryWeekMetrics[];
};

export type LeadOutcomeValue =
  | "contacted"
  | "no_response"
  | "replied_positive"
  | "replied_negative"
  | "meeting_booked"
  | "won"
  | "not_a_fit"
  | "wrong_contact"
  | "business_closed"
  | "bounced"
  | "unsubscribed";

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

export type CampaignOutreachAudience = "selected" | "ready_contacts" | "ready_shortlist";

export type CampaignOutreachDraftInput = {
  audience?: CampaignOutreachAudience;
  lead_ids?: string[];
  subject: string;
  body: string;
  approach_tag?: string;
};

export type CampaignMessageApprovalInput = {
  message_ids?: string[];
  approved_by: string;
  notes?: string | null;
};

export type CampaignMessageSendInput = {
  message_ids?: string[];
};

export type CampaignMessageSkip = {
  lead_id?: string | null;
  message_id?: string | null;
  company_name?: string | null;
  reason: string;
};

export type CampaignMessageBatchResult = {
  messages: Message[];
  skipped: CampaignMessageSkip[];
  created_count: number;
  reused_count: number;
  approved_count: number;
  sent_count: number;
  failed_count: number;
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

export type RunPipelineEvent = {
  id: string;
  campaign_id: string;
  segment_id?: string | null;
  job_id?: string | null;
  stage: string;
  event_type: string;
  status: string;
  provider_id?: string | null;
  business_id?: string | null;
  lead_id?: string | null;
  item_key?: string | null;
  request_payload?: Record<string, unknown> | null;
  response_payload?: Record<string, unknown> | null;
  reason?: string | null;
  created_at: string;
  updated_at: string;
};

export type SourceItemDecision = {
  id: string;
  source_item_id: string;
  stage: "relevance" | "identity" | "opportunity" | "eligibility";
  decision: "accepted" | "rejected" | "needs_review" | "duplicate" | "resolved" | "audited" | "eligible" | "excluded" | "failed";
  reason?: string | null;
  confidence?: number | null;
  details: Record<string, unknown>;
  actor_type: string;
  actor_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type SourceItem = {
  id: string;
  segment_id: string;
  job_id?: string | null;
  provider_id: string;
  external_id?: string | null;
  query: string;
  source_url?: string | null;
  title?: string | null;
  raw_payload: Record<string, unknown>;
  fetched_at: string;
  content_hash: string;
  state: "fetched" | "needs_review" | "relevant" | "rejected" | "identity_resolved" | "audit_pending" | "audited" | "eligible" | "excluded" | "failed";
  business_id?: string | null;
  last_error?: string | null;
  decisions: SourceItemDecision[];
  created_at: string;
  updated_at: string;
};

export type RunSourceDiagnostic = {
  key: string;
  provider_id: string;
  query: string;
  quota: number;
  status: string;
  fetched_count: number;
  accepted_count?: number | null;
  rejected_count?: number | null;
  written_count: number;
  final_count: number;
  failure?: string | null;
  request: Record<string, unknown>;
  state: Record<string, unknown>;
  exact_decisions: boolean;
};

export type RunJobDiagnostic = {
  id: string;
  type: string;
  status: string;
  attempts: number;
  max_attempts: number;
  payload: Record<string, unknown>;
  last_error?: string | null;
  run_after: string;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type RunDiagnostics = {
  run_id: string;
  run_name: string;
  run_status: string;
  run_stage: string;
  created_at: string;
  updated_at: string;
  retention: "exact" | "aggregate_only";
  request: Record<string, unknown>;
  segment?: Record<string, unknown> | null;
  summary: {
    requested?: number | null;
    existing_matches?: number | null;
    fetched?: number | null;
    accepted?: number | null;
    rejected?: number | null;
    failed_sources?: number | null;
    final?: number | null;
  };
  sources: RunSourceDiagnostic[];
  jobs: RunJobDiagnostic[];
  events: RunPipelineEvent[];
  final_results: DiscoveryResult[];
  caveats: string[];
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
export type AdminOverview = {
  total: number;
  active: number;
  quarantined: number;
  archived: number;
  fully_validated: number;
  needs_attention: number;
  incomplete: number;
  published: number;
};

export type AdminBusinessSummary = {
  id: string;
  display_name: string;
  status: string;
  validation_state: "passed" | "attention" | "incomplete";
  website_url?: string | null;
  domain?: string | null;
  phone?: string | null;
  address?: string | null;
  geography?: string | null;
  market_key?: string | null;
  niche_slug?: string | null;
  niche_label?: string | null;
  last_seen_at: string;
};

export type AdminValidation = {
  id: string;
  type: string;
  status: string;
  confidence: number;
  reason: string;
  evidence: Array<Record<string, unknown>>;
  observed_at: string;
  expires_at: string;
};

export type AdminBusinessDetail = AdminBusinessSummary & {
  normalized_name: string;
  latitude?: number | null;
  longitude?: number | null;
  customer_kind: string;
  is_chain?: boolean | null;
  is_franchise?: boolean | null;
  is_directory?: boolean | null;
  is_agency?: boolean | null;
  memberships: Array<Record<string, unknown>>;
  validations: AdminValidation[];
  facts: Array<Record<string, unknown>>;
  sources: Array<Record<string, unknown>>;
  publications: Array<Record<string, unknown>>;
  audit: Array<Record<string, unknown>>;
  delete_dependencies: Record<string, number>;
};

export type AdminBusinessPage = {
  items: AdminBusinessSummary[];
  total: number;
  page: number;
  page_size: number;
};
