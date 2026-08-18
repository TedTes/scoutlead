import type {
  ApiHealth,
  AgentRun,
  AgentRunDetail,
  Campaign,
  CampaignCreateInput,
  CampaignPreflight,
  CampaignRunSummary,
  ConnectionStatus,
  Conversation,
  Lead,
  Message,
  Metrics,
  ManualClassificationInput,
  Product,
  ProductDescriptionInput,
} from "../types/domain";

type ApiOptions = {
  baseUrl: string;
  token?: string;
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

  updateProduct(id: string, product: unknown) {
    return this.request<Product>(`/products/${id}`, { method: "PATCH", body: product });
  }

  deleteProduct(id: string) {
    return this.request<void>(`/products/${id}`, { method: "DELETE" });
  }

  getCampaigns() {
    return this.request<Campaign[]>("/campaigns");
  }

  createCampaign(input: CampaignCreateInput) {
    return this.request<Campaign>("/campaigns", { method: "POST", body: input });
  }

  getCampaign(id: string) {
    return this.request<Campaign>(`/campaigns/${id}`);
  }

  getCampaignPreflight(id: string) {
    return this.request<CampaignPreflight>(`/campaigns/${id}/preflight`);
  }

  deleteCampaign(id: string) {
    return this.request<void>(`/campaigns/${id}`, { method: "DELETE" });
  }

  runCampaign(id: string) {
    return this.request<CampaignRunSummary>(`/campaigns/${id}/run`, { method: "POST" });
  }

  enqueueCampaign(id: string) {
    return this.request<AgentRun>(`/campaigns/${id}/enqueue`, { method: "POST" });
  }

  getCampaignAgentRuns(campaignId: string) {
    return this.request<AgentRun[]>(`/campaigns/${campaignId}/agent-runs`);
  }

  getAgentRun(id: string) {
    return this.request<AgentRunDetail>(`/agent-runs/${id}`);
  }

  pauseCampaign(id: string) {
    return this.request<Campaign>(`/campaigns/${id}/pause`, { method: "POST" });
  }

  resumeCampaign(id: string) {
    return this.request<Campaign>(`/campaigns/${id}/resume`, { method: "POST" });
  }

  addSeedLeads(campaignId: string, seeds: unknown[]) {
    return this.request<Lead[]>(`/campaigns/${campaignId}/leads/seeds`, {
      method: "POST",
      body: seeds,
    });
  }

  getLeads(campaignId: string) {
    return this.request<Lead[]>(`/campaigns/${campaignId}/leads`);
  }

  getMessages(campaignId: string) {
    return this.request<Message[]>(`/campaigns/${campaignId}/messages`);
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

  cancelMessage(id: string) {
    return this.request<Message>(`/messages/${id}/cancel`, { method: "POST" });
  }

  getConversations(campaignId: string) {
    return this.request<Conversation[]>(`/campaigns/${campaignId}/conversations`);
  }

  recordResponse(conversationId: string, body: string) {
    return this.request<Conversation>(`/conversations/${conversationId}/responses`, {
      method: "POST",
      body: { body },
    });
  }

  manuallyClassifyResponse(conversationId: string, classification: ManualClassificationInput) {
    return this.request<Conversation>(`/conversations/${conversationId}/classification`, {
      method: "POST",
      body: classification,
    });
  }

  getMetrics(campaignId: string) {
    return this.request<Metrics>(`/campaigns/${campaignId}/metrics`);
  }

  getConnectionsStatus() {
    return this.request<ConnectionStatus[]>("/connections/status");
  }

  private async request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
    const response = await fetch(`${this.options.baseUrl.replace(/\/$/, "")}${path}`, {
      method: init.method ?? "GET",
      headers: {
        "content-type": "application/json",
        ...(this.options.token ? { authorization: `Bearer ${this.options.token}` } : {}),
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
    const payload = response.status === 204 ? undefined : await response.json().catch(() => undefined);
    if (!response.ok) {
      const message = payload?.error?.message ?? `Request failed with ${response.status}`;
      throw new Error(message);
    }
    return payload as T;
  }
}
