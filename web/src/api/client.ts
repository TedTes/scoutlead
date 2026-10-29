import type {
  AdminBusinessDetail,
  AdminBusinessPage,
  AdminOverview,
  AdminDataJob,
  AdminDataSegment,
  AdminSignalDefinition,
  AdminSignalDefinitionInput,
  AdminServiceDefinition,
  AdminServiceDefinitionInput,
  ApiHealth,
  DiscoveryRun,
  DiscoveryRunCreateInput,
  DiscoveryRunSource,
  DiscoveryCandidate,
  DiscoveryResult,
  OutreachPackage,
  OutreachChannel,
  OutreachDraftAlternative,
  OutreachResponseClassification,
  OutreachAnalytics,
  AdminOutreachPlaybook,
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
  ProfileOptions,
  ProfileQueued,
  SourceRequestInput,
  SourceRequestRun,
  SourceProvider,
  GmailAuthorizationUrl,
  GmailConnectionStatus,
  WebhookDelivery,
  Territory,
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

  getAdminAccess() {
    return this.request<{ is_admin: boolean; email?: string | null }>("/admin/access");
  }

  getAdminOverview() {
    return this.request<AdminOverview>("/admin/businesses/overview");
  }

  getAdminBusinesses(params: Record<string, string | number | undefined>) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return this.request<AdminBusinessPage>(`/admin/businesses?${query.toString()}`);
  }

  getAdminBusiness(id: string) {
    return this.request<AdminBusinessDetail>(`/admin/businesses/${id}`);
  }

  createAdminBusiness(body: Record<string, unknown>) {
    return this.request<AdminBusinessDetail>("/admin/businesses", { method: "POST", body });
  }

  updateAdminBusiness(id: string, body: Record<string, unknown>) {
    return this.request<AdminBusinessDetail>(`/admin/businesses/${id}`, { method: "PATCH", body });
  }

  changeAdminBusinessStatus(id: string, status: string, reason: string) {
    return this.request<AdminBusinessDetail>(`/admin/businesses/${id}/status`, {
      method: "POST",
      body: { status, reason },
    });
  }

  revalidateAdminBusiness(id: string, reason: string) {
    return this.request<AdminBusinessDetail>(`/admin/businesses/${id}/revalidate`, {
      method: "POST",
      body: { reason },
    });
  }

  getAdminBusinessDeleteDependencies(id: string) {
    return this.request<Record<string, number>>(`/admin/businesses/${id}/delete-dependencies`);
  }

  deleteAdminBusiness(id: string, confirmation: string, reason: string) {
    return this.request<void>(`/admin/businesses/${id}`, {
      method: "DELETE",
      body: { confirmation, reason },
    });
  }

  getAdminDataSegments() {
    return this.request<AdminDataSegment[]>("/admin/data-jobs/segments");
  }

  getAdminDataJobs() {
    return this.request<AdminDataJob[]>("/admin/data-jobs");
  }

  getAdminDataJob(id: string) {
    return this.request<AdminDataJob>(`/admin/data-jobs/${id}`);
  }

  createAdminDataJob(body: { segment_id: string; processing_mode: "automatic" | "review_first"; reason: string }) {
    return this.request<AdminDataJob>("/admin/data-jobs", { method: "POST", body });
  }

  validateAdminDataJob(id: string, reason: string, sourceItemIds: string[] = []) {
    return this.request<AdminDataJob>(`/admin/data-jobs/${id}/validate`, {
      method: "POST",
      body: { reason, source_item_ids: sourceItemIds },
    });
  }

  discardAdminDataJob(id: string, reason: string) {
    return this.request<AdminDataJob>(`/admin/data-jobs/${id}/discard`, {
      method: "POST",
      body: { reason },
    });
  }

  cancelAdminDataJob(id: string, reason: string) {
    return this.request<AdminDataJob>(`/admin/data-jobs/${id}/cancel`, {
      method: "POST",
      body: { reason },
    });
  }

  retryAdminDataJob(id: string, reason: string) {
    return this.request<AdminDataJob>(`/admin/data-jobs/${id}/retry`, {
      method: "POST",
      body: { reason },
    });
  }

  getAdminSignals(status = "") {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return this.request<AdminSignalDefinition[]>(`/admin/signals${query}`);
  }

  createAdminSignal(body: AdminSignalDefinitionInput) {
    return this.request<AdminSignalDefinition>("/admin/signals", { method: "POST", body });
  }

  changeAdminSignalStatus(id: string, status: "draft" | "active" | "inactive", reason: string) {
    return this.request<AdminSignalDefinition>(`/admin/signals/${id}/status`, {
      method: "POST",
      body: { status, reason, scope: "all", batch_size: 25 },
    });
  }

  collectAdminSignal(id: string, reason: string, businessIds: string[] = []) {
    return this.request<{ signal: AdminSignalDefinition; collection_jobs: AdminSignalDefinition["collection_jobs"] }>(`/admin/signals/${id}/collect`, {
      method: "POST",
      body: {
        reason,
        scope: businessIds.length ? "selected" : "all",
        business_ids: businessIds,
        batch_size: 25,
      },
    });
  }

  collectActiveAdminSignals(reason: string) {
    return this.request<{ definition_count: number; job_count: number }>("/admin/signals/collect-active", {
      method: "POST",
      body: { reason, scope: "all", batch_size: 10 },
    });
  }

  validateAdminSignal(id: string, decision: "approve" | "reject", reason: string, businessIds: string[] = []) {
    return this.request<{ signal: AdminSignalDefinition; decision: string; affected_count: number; business_ids: string[] }>(`/admin/signals/${id}/validate`, {
      method: "POST",
      body: {
        decision,
        reason,
        scope: businessIds.length ? "selected" : "all",
        business_ids: businessIds,
      },
    });
  }

  getAdminServices(status = "") {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return this.request<AdminServiceDefinition[]>(`/admin/services${query}`);
  }

  createAdminService(body: AdminServiceDefinitionInput) {
    return this.request<AdminServiceDefinition>("/admin/services", { method: "POST", body });
  }

  updateAdminService(id: string, body: Omit<AdminServiceDefinitionInput, "key">) {
    return this.request<AdminServiceDefinition>(`/admin/services/${id}`, { method: "PATCH", body });
  }

  changeAdminServiceStatus(id: string, status: "draft" | "active" | "inactive", reason: string) {
    return this.request<AdminServiceDefinition>(`/admin/services/${id}/status`, {
      method: "POST",
      body: { status, reason },
    });
  }

  collectAdminService(id: string, reason: string) {
    return this.request<{ service: AdminServiceDefinition; signal_count: number; collection_jobs: unknown[] }>(`/admin/services/${id}/collect`, {
      method: "POST",
      body: { reason, scope: "all", business_ids: [], batch_size: 10 },
    });
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

  getDiscoveryRuns() {
    return this.request<DiscoveryRun[]>("/discovery-runs");
  }

  getTerritories() {
    return this.request<Territory[]>("/audiences");
  }

  getAudienceFolders(productId: string) {
    return this.request<import("../types/domain").AudienceFolder[]>(
      `/audience-folders?product_id=${encodeURIComponent(productId)}`,
    );
  }

  createAudienceFolder(productId: string, name: string) {
    return this.request<import("../types/domain").AudienceFolder>("/audience-folders", {
      method: "POST",
      body: { product_id: productId, name },
    });
  }

  renameAudienceFolder(folderId: string, name: string) {
    return this.request<import("../types/domain").AudienceFolder>(`/audience-folders/${folderId}`, {
      method: "PATCH",
      body: { name },
    });
  }

  deleteAudienceFolder(folderId: string) {
    return this.request<void>(`/audience-folders/${folderId}`, { method: "DELETE" });
  }

  getAudiencePerformance(productId?: string) {
    const query = productId ? `?product_id=${encodeURIComponent(productId)}` : "";
    return this.request<import("../types/domain").AudiencePerformance[]>(
      `/audiences/summary${query}`,
    );
  }

  getWorkspaceOverview() {
    return this.request<import("../types/domain").WorkspaceAudienceOverview>(
      "/audiences/overview",
    );
  }

  getWorkspaceLeads(input: { view?: string; limit?: number; offset?: number; search?: string } = {}) {
    const params = new URLSearchParams();
    if (input.view) params.set("view", input.view);
    if (input.limit !== undefined) params.set("limit", String(input.limit));
    if (input.offset !== undefined) params.set("offset", String(input.offset));
    if (input.search?.trim()) params.set("search", input.search.trim());
    const query = params.toString();
    return this.request<import("../types/domain").WorkspaceLeadPage>(
      `/leads${query ? `?${query}` : ""}`,
    );
  }

  getProfileOptions() {
    return this.request<ProfileOptions>("/audiences/options");
  }

  createProfile(input: ProfileCreateInput) {
    return this.request<ProfileQueued>("/audiences", { method: "POST", body: input });
  }

  updateProfile(id: string, update: Partial<Territory>) {
    return this.request<Territory>(`/audiences/${id}`, { method: "PATCH", body: update });
  }

  searchPlaces(query: string) {
    return this.request<import("../types/domain").PlaceOption[]>(`/audiences/places?q=${encodeURIComponent(query)}`);
  }

  deleteProfile(id: string) {
    return this.request<void>(`/audiences/${id}`, { method: "DELETE" });
  }

  refillProfile(id: string) {
    return this.request<ProfileQueued>(`/audiences/${id}/refill`, { method: "POST" });
  }

  getProfileBatch(id: string) {
    return this.request<ProfileBatch>(`/audiences/${id}/current-batch`);
  }

  getOutreachPackage(resultId: string) {
    return this.request<OutreachPackage | null>(`/outreach-packages/by-result/${resultId}`);
  }

  generateOutreachPackage(resultId: string) {
    return this.request<OutreachPackage>(`/outreach-packages/from-result/${resultId}`, { method: "POST" });
  }

  updateOutreachPackage(id: string, content: OutreachPackage["content"]) {
    return this.request<OutreachPackage>(`/outreach-packages/${id}`, {
      method: "PATCH",
      body: { content },
    });
  }

  generateOutreachAISuggestion(id: string, channel: Exclude<OutreachChannel, "call">) {
    return this.request<OutreachDraftAlternative>(`/outreach-packages/${id}/ai-suggestion`, {
      method: "POST",
      body: { channel },
    });
  }

  classifyOutreachResponse(id: string, channel: OutreachChannel, responseText: string) {
    return this.request<OutreachResponseClassification>(`/outreach-packages/${id}/classify-response`, {
      method: "POST",
      body: { channel, response_text: responseText },
    });
  }

  recordOutreachEvent(
    id: string,
    event: { channel: OutreachChannel; event_type: string; variant_id?: string | null; metadata?: Record<string, unknown> },
  ) {
    return this.request(`/outreach-packages/${id}/events`, { method: "POST", body: event });
  }

  prepareOutreachMessage(id: string) {
    return this.request<Message>(`/outreach-packages/${id}/message`, { method: "POST" });
  }

  getOutreachAnalytics() {
    return this.request<OutreachAnalytics>("/outreach-packages/analytics/summary");
  }

  getAdminOutreachPlaybooks() {
    return this.request<AdminOutreachPlaybook[]>("/admin/outreach-playbooks");
  }

  updateAdminOutreachPlaybook(serviceKey: string, definition: Record<string, unknown>, reason: string) {
    return this.request<AdminOutreachPlaybook>(`/admin/outreach-playbooks/${encodeURIComponent(serviceKey)}`, {
      method: "PUT",
      body: { definition, reason },
    });
  }

  changeAdminOutreachPlaybookStatus(serviceKey: string, status: "draft" | "active" | "inactive", reason: string) {
    return this.request<AdminOutreachPlaybook>(`/admin/outreach-playbooks/${encodeURIComponent(serviceKey)}/status`, {
      method: "POST",
      body: { status, reason },
    });
  }

  resolveTerritory(productId: string, request: string) {
    return this.request<TerritoryResolution>("/audiences/resolve", {
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
    return this.request<Territory>("/audiences/from-resolution", {
      method: "POST",
      body: { ...resolution, ...settings, confirmed: true },
    });
  }

  updateTerritory(id: string, update: Partial<Pick<Territory, "label" | "status" | "batch_size" | "min_fit" | "refill_policy">>) {
    return this.request<Territory>(`/audiences/${id}`, { method: "PATCH", body: update });
  }

  refreshTerritory(id: string) {
    return this.request<ProfileQueued>(`/audiences/${id}/refill`, { method: "POST" });
  }

  getTerritoryMetrics(id: string, weeks = 8) {
    return this.request<TerritoryMetrics>(`/audiences/${id}/metrics?weeks=${weeks}`);
  }

  async recordLeadOutcome(leadId: string, outcome: LeadOutcomeValue, channel = "other") {
    const resolvedId = leadId.startsWith("audience_result_")
      ? (await this.promoteAudienceResult(leadId)).id
      : leadId;
    return this.request(`/leads/${resolvedId}/outcomes`, {
      method: "POST",
      body: { outcome, channel },
    });
  }

  async generateLeadApproach(leadId: string) {
    const resolvedId = leadId.startsWith("audience_result_")
      ? (await this.promoteAudienceResult(leadId)).id
      : leadId;
    return this.request<DiscoveryResult>(`/leads/${resolvedId}/approach`, { method: "POST" });
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

  deleteDiscoveryRun(id: string) {
    return this.request<void>(`/discovery-runs/${id}`, { method: "DELETE" });
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
    const path = id.startsWith("audience_result_")
      ? `/audiences/results/${id}`
      : `/leads/${id}`;
    return this.request<DiscoveryResult>(path, { method: "PATCH", body });
  }

  updateLeadContactPolicy(id: string, body: LeadContactPolicyInput) {
    const path = id.startsWith("audience_result_")
      ? `/audiences/results/${id}/contact-policy`
      : `/leads/${id}/contact-policy`;
    return this.request<DiscoveryResult>(path, { method: "PATCH", body });
  }

  qualifyLead(id: string) {
    if (id.startsWith("audience_result_")) {
      return this.updateLead(id, { review_status: "good_fit" });
    }
    return this.request<DiscoveryResult>(`/leads/${id}/qualify`, { method: "POST" });
  }

  getDiscoveryCandidates(runId: string) {
    return this.request<DiscoveryCandidate[]>(`/discovery-runs/${runId}/discovery-candidates`);
  }

  getMessages(runId: string) {
    return this.request<Message[]>(`/discovery-runs/${runId}/messages`);
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

  promoteAudienceResult(resultId: string) {
    return this.request<DiscoveryResult>(
      `/audiences/results/${resultId}/outreach-lead`,
      { method: "POST" },
    );
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
