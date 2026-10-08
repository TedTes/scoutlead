import type {
  ApiHealth,
  AgentRun,
  AgentRunDetail,
  DiscoveryRun,
  DiscoveryRunCreateInput,
  DiscoveryPreflight,
  DiscoveryRunSummary,
  DiscoveryRunSource,
  DiscoveryTrace,
  DiscoveryCandidate,
  DiscoveryResult,
  RunDiagnostics,
  SourceItem,
  CampaignMessageApprovalInput,
  CampaignMessageBatchResult,
  CampaignMessageSendInput,
  CampaignOutreachDraftInput,
  LeadContactPolicyInput,
  LeadUpdateInput,
  Message,
  Metrics,
  Product,
  ProductDescriptionInput,
  ProductProfileInput,
  ProfileBatch,
  ProfileCreateInput,
  ProfileFactChange,
  ProfileOptions,
  ProfileQueued,
  SourceRequestInput,
  SourceRequestRun,
  SourceProvider,
  GmailAuthorizationUrl,
  GmailConnectionStatus,
  WebhookDelivery,
  Territory,
  TerritoryDelivery,
  TerritoryMetrics,
  TerritoryResolution,
  LeadOutcomeValue,
  SenderProfile,
} from "../types/domain";

type ApiOptions = {
  baseUrl: string;
  token?: string;
  getToken?: () => Promise<string | null>;
};

export class ApiClient {
  constructor(private options: ApiOptions) {}

  getProducts() {
    return this.request<Product[]>("/products");
  }

  getHealth() {
    return this.request<ApiHealth>("/health");
  }

  createProduct(product: unknown) {
    return this.request<Product>("/products", { method: "POST", body: product });
  }

  createProductFromDescription(input: ProductDescriptionInput) {
    return this.request<Product>("/products/from-description", { method: "POST", body: input });
  }

  createProductFromProfile(input: ProductProfileInput) {
    return this.request<Product>("/products/from-profile", { method: "POST", body: input });
  }

  updateProduct(id: string, product: unknown) {
    return this.request<Product>(`/products/${id}`, { method: "PATCH", body: product });
  }

  deleteProduct(id: string) {
    return this.request<void>(`/products/${id}`, { method: "DELETE" });
  }

  getGmailConnectionStatus(productId: string) {
    return this.request<GmailConnectionStatus>(`/products/${productId}/email/gmail/status`);
  }

  getGmailAuthorizationUrl(productId: string) {
    return this.request<GmailAuthorizationUrl>(`/products/${productId}/email/gmail/connect`);
  }

  getSenderProfile() {
    return this.request<SenderProfile>("/workspace/sender-profile");
  }

  updateSenderProfile(update: Partial<Omit<SenderProfile, "workspace_id" | "complete">>) {
    return this.request<SenderProfile>("/workspace/sender-profile", {
      method: "PATCH",
      body: update,
    });
  }

  disconnectGmail(productId: string) {
    return this.request<GmailConnectionStatus>(`/products/${productId}/email/gmail`, { method: "DELETE" });
  }

  discoverProduct(id: string, maxResults = 10) {
    return this.request<DiscoveryRunSummary>(`/products/${id}/discover`, {
      method: "POST",
      body: { max_results: maxResults },
    });
  }

  getDiscoveryRuns() {
    return this.request<DiscoveryRun[]>("/discovery-runs");
  }

  getTerritories() {
    return this.request<Territory[]>("/territories");
  }

  getProfiles() {
    return this.request<Territory[]>("/profiles");
  }

  getProfileOptions() {
    return this.request<ProfileOptions>("/profiles/options");
  }

  createProfile(input: ProfileCreateInput) {
    return this.request<ProfileQueued>("/profiles", { method: "POST", body: input });
  }

  updateProfile(id: string, update: Partial<Territory>) {
    return this.request<Territory>(`/profiles/${id}`, { method: "PATCH", body: update });
  }

  deleteProfile(id: string) {
    return this.request<void>(`/profiles/${id}`, { method: "DELETE" });
  }

  refillProfile(id: string) {
    return this.request<ProfileQueued>(`/profiles/${id}/refill`, { method: "POST" });
  }

  getProfileBatch(id: string) {
    return this.request<ProfileBatch>(`/profiles/${id}/current-batch`);
  }

  getProfileChanges(id: string, since?: string) {
    const query = since ? `?since=${encodeURIComponent(since)}` : "";
    return this.request<ProfileFactChange[]>(`/profiles/${id}/changes${query}`);
  }

  resolveTerritory(productId: string, request: string) {
    return this.request<TerritoryResolution>("/territories/resolve", {
      method: "POST",
      body: { product_id: productId, request },
    });
  }

  createTerritory(
    resolution: TerritoryResolution,
    settings: Partial<
      Pick<
        Territory,
        "label" | "batch_size" | "min_fit" | "refill_policy" | "search_contract" | "evidence_max_age_days"
      >
    > = {},
  ) {
    return this.request<Territory>("/territories", {
      method: "POST",
      body: { ...resolution, ...settings, confirmed: true },
    });
  }

  updateTerritory(id: string, update: Partial<Pick<Territory, "label" | "status" | "batch_size" | "min_fit" | "refill_policy">>) {
    return this.request<Territory>(`/territories/${id}`, { method: "PATCH", body: update });
  }

  deleteTerritory(id: string) {
    return this.request<void>(`/territories/${id}`, { method: "DELETE" });
  }

  refreshTerritory(id: string) {
    return this.request<ProfileQueued>(`/territories/${id}/refresh`, { method: "POST" });
  }

  getTerritoryDeliveries(id: string) {
    return this.request<TerritoryDelivery[]>(`/territories/${id}/deliveries`);
  }

  getTerritoryDeliveryContacts(territoryId: string, deliveryId: string) {
    return this.request<DiscoveryResult[]>(`/territories/${territoryId}/deliveries/${deliveryId}/contacts`);
  }

  async downloadTerritoryDeliveryCsv(territoryId: string, deliveryId: string) {
    const authToken = (await this.options.getToken?.()) || this.options.token;
    const path = `/territories/${territoryId}/deliveries/${deliveryId}/export.csv`;
    const response = await fetch(`${this.options.baseUrl.replace(/\/$/, "")}${path}`, {
      headers: authToken ? { authorization: `Bearer ${authToken}` } : {},
    });
    if (!response.ok) throw new Error(`Export failed with ${response.status}`);
    return response.blob();
  }

  getTerritoryMetrics(id: string, weeks = 8) {
    return this.request<TerritoryMetrics>(`/territories/${id}/metrics?weeks=${weeks}`);
  }

  recordLeadOutcome(leadId: string, outcome: LeadOutcomeValue, channel = "other") {
    return this.request(`/leads/${leadId}/outcomes`, {
      method: "POST",
      body: { outcome, channel },
    });
  }

  generateLeadApproach(leadId: string) {
    return this.request<DiscoveryResult>(`/leads/${leadId}/approach`, { method: "POST" });
  }

  createDiscoveryRun(input: DiscoveryRunCreateInput) {
    return this.request<DiscoveryRun>("/discovery-runs", { method: "POST", body: input });
  }

  createSourceRequest(input: SourceRequestInput) {
    return this.request<SourceRequestRun>("/discovery-runs/source-request", { method: "POST", body: input });
  }

  rerunSourceRequest(runId: string) {
    return this.request<SourceRequestRun>(`/discovery-runs/${runId}/rerun`, { method: "POST" });
  }

  getSourceProviders() {
    return this.request<SourceProvider[]>("/discovery-runs/source-providers");
  }

  getDiscoveryRun(id: string) {
    return this.request<DiscoveryRun>(`/discovery-runs/${id}`);
  }

  updateDiscoveryRun(id: string, body: Partial<Pick<DiscoveryRun, "name" | "territory_id">>) {
    return this.request<DiscoveryRun>(`/discovery-runs/${id}`, { method: "PATCH", body });
  }

  getDiscoveryRunSources(id: string) {
    return this.request<DiscoveryRunSource[]>(`/discovery-runs/${id}/sources`);
  }

  getDiscoveryRunPreflight(id: string) {
    return this.request<DiscoveryPreflight>(`/discovery-runs/${id}/preflight`);
  }

  deleteDiscoveryRun(id: string) {
    return this.request<void>(`/discovery-runs/${id}`, { method: "DELETE" });
  }

  runDiscovery(id: string) {
    return this.request<DiscoveryRunSummary>(`/discovery-runs/${id}/run`, { method: "POST" });
  }

  enqueueDiscoveryRun(id: string) {
    return this.request<AgentRun>(`/discovery-runs/${id}/enqueue`, { method: "POST" });
  }

  getDiscoveryRunAgentRuns(runId: string) {
    return this.request<AgentRun[]>(`/discovery-runs/${runId}/agent-runs`);
  }

  getDiscoveryTrace(runId: string) {
    return this.request<DiscoveryTrace>(`/discovery-runs/${runId}/trace`);
  }

  getDiscoveryRunDiagnostics(runId: string) {
    return this.request<RunDiagnostics>(`/discovery-runs/${runId}/diagnostics`);
  }

  getDiscoveryRunSourceItems(runId: string) {
    return this.request<SourceItem[]>(`/discovery-runs/${runId}/source-items`);
  }

  reviewDiscoveryRunSourceItem(
    runId: string,
    sourceItemId: string,
    action: "accept" | "reject" | "duplicate" | "reaudit",
  ) {
    return this.request<SourceItem>(`/discovery-runs/${runId}/source-items/${sourceItemId}/review`, {
      method: "POST",
      body: { action },
    });
  }

  getAgentRun(id: string) {
    return this.request<AgentRunDetail>(`/agent-runs/${id}`);
  }

  pauseDiscoveryRun(id: string) {
    return this.request<DiscoveryRun>(`/discovery-runs/${id}/pause`, { method: "POST" });
  }

  resumeDiscoveryRun(id: string) {
    return this.request<DiscoveryRun>(`/discovery-runs/${id}/resume`, { method: "POST" });
  }

  addSeedResults(runId: string, seeds: unknown[]) {
    return this.request<DiscoveryResult[]>(`/discovery-runs/${runId}/results/seeds`, {
      method: "POST",
      body: seeds,
    });
  }

  getResults(runId: string) {
    return this.request<DiscoveryResult[]>(`/discovery-runs/${runId}/results`);
  }

  updateLead(id: string, body: LeadUpdateInput) {
    return this.request<DiscoveryResult>(`/leads/${id}`, { method: "PATCH", body });
  }

  updateLeadContactPolicy(id: string, body: LeadContactPolicyInput) {
    return this.request<DiscoveryResult>(`/leads/${id}/contact-policy`, { method: "PATCH", body });
  }

  qualifyLead(id: string) {
    return this.request<DiscoveryResult>(`/leads/${id}/qualify`, { method: "POST" });
  }

  getDiscoveryCandidates(runId: string) {
    return this.request<DiscoveryCandidate[]>(`/discovery-runs/${runId}/discovery-candidates`);
  }

  getMessages(runId: string) {
    return this.request<Message[]>(`/discovery-runs/${runId}/messages`);
  }

  getWebhookDeliveries(runId: string) {
    return this.request<WebhookDelivery[]>(`/discovery-runs/${runId}/webhook-deliveries`);
  }

  sendApprovedShortlistWebhook(runId: string) {
    return this.request<WebhookDelivery>(`/discovery-runs/${runId}/webhook-deliveries`, {
      method: "POST",
      body: { event: "approved_shortlist.ready" },
    });
  }

  draftShortlist(runId: string) {
    return this.request<Message[]>(`/discovery-runs/${runId}/draft-shortlist`, { method: "POST" });
  }

  createCampaignDrafts(runId: string, input: CampaignOutreachDraftInput) {
    return this.request<CampaignMessageBatchResult>(`/discovery-runs/${runId}/campaign-drafts`, {
      method: "POST",
      body: input,
    });
  }

  approveCampaignDrafts(runId: string, input: CampaignMessageApprovalInput) {
    return this.request<CampaignMessageBatchResult>(`/discovery-runs/${runId}/campaign-drafts/approve`, {
      method: "POST",
      body: input,
    });
  }

  sendCampaignDrafts(runId: string, input: CampaignMessageSendInput = {}) {
    return this.request<CampaignMessageBatchResult>(`/discovery-runs/${runId}/campaign-drafts/send`, {
      method: "POST",
      body: input,
    });
  }

  createLeadOutreachDraft(leadId: string) {
    return this.request<Message>(`/leads/${leadId}/outreach-draft`, { method: "POST" });
  }

  updateMessage(id: string, body: Partial<Message>) {
    return this.request<Message>(`/messages/${id}`, { method: "PATCH", body });
  }

  approveMessage(id: string, approvedBy: string) {
    return this.request<Message>(`/messages/${id}/approve`, {
      method: "POST",
      body: { approved_by: approvedBy },
    });
  }

  sendMessage(id: string) {
    return this.request<Message>(`/messages/${id}/send`, { method: "POST" });
  }

  markMessageReplied(id: string, body?: string) {
    return this.request<Message>(`/messages/${id}/mark-replied`, {
      method: "POST",
      body: { body: body || undefined },
    });
  }

  cancelMessage(id: string) {
    return this.request<Message>(`/messages/${id}/cancel`, { method: "POST" });
  }

  getMetrics(runId: string) {
    return this.request<Metrics>(`/discovery-runs/${runId}/metrics`);
  }

  private async request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
    const authToken = (await this.options.getToken?.()) || this.options.token;
    const response = await fetch(`${this.options.baseUrl.replace(/\/$/, "")}${path}`, {
      method: init.method ?? "GET",
      headers: {
        "content-type": "application/json",
        ...(authToken ? { authorization: `Bearer ${authToken}` } : {}),
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
    const payload = response.status === 204 ? undefined : await response.json().catch(() => undefined);
    if (!response.ok) {
      const details = payload?.error?.details;
      const userMessage = details && typeof details === "object" ? details.user_message : undefined;
      const detailText =
        !userMessage && details && typeof details === "object"
          ? [details.required_shape, details.query ? `Query: ${details.query}` : undefined]
              .filter(Boolean)
              .join(" ")
          : "";
      const message = [userMessage ?? payload?.error?.message ?? `Request failed with ${response.status}`, detailText]
        .filter(Boolean)
        .join(" ");
      throw new Error(message);
    }
    return payload as T;
  }
}
