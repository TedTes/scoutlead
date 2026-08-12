export type Product = {
  id: string;
  product_name: string;
  target_customer: string;
  target_geography: string;
  validation_goal: string;
  [key: string]: unknown;
};

export type Campaign = {
  id: string;
  product_id: string;
  name?: string;
  status: string;
  stage: string;
  max_leads: number;
  channels: string[];
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
  research?: {
    summary: string;
    signals: string[];
    pain_indicators: string[];
    confidence: number;
  };
  qualification?: {
    qualified: boolean;
    score: number;
    rationale: string;
  };
};

export type Message = {
  id: string;
  campaign_id: string;
  lead_id: string;
  channel: string;
  subject?: string;
  body: string;
  personalization_notes: string[];
  approach_tag: string;
  status: string;
};

export type Conversation = {
  id: string;
  lead_id: string;
  status: string;
  events: Array<{
    id: string;
    direction: string;
    body: string;
    classification?: {
      intent: string;
      confidence: number;
      rationale: string;
      follow_up_action: string;
    };
  }>;
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

type ApiOptions = {
  baseUrl: string;
  token?: string;
};

export class ApiClient {
  constructor(private options: ApiOptions) {}

  getProducts() {
    return this.request<Product[]>("/products");
  }

  createProduct(product: unknown) {
    return this.request<Product>("/products", { method: "POST", body: product });
  }

  getCampaigns() {
    return this.request<Campaign[]>("/campaigns");
  }

  createCampaign(input: unknown) {
    return this.request<Campaign>("/campaigns", { method: "POST", body: input });
  }

  getCampaign(id: string) {
    return this.request<Campaign>(`/campaigns/${id}`);
  }

  runCampaign(id: string) {
    return this.request(`/campaigns/${id}/run`, { method: "POST" });
  }

  enqueueCampaign(id: string) {
    return this.request(`/campaigns/${id}/enqueue`, { method: "POST" });
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

  getMetrics(campaignId: string) {
    return this.request<Metrics>(`/campaigns/${campaignId}/metrics`);
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
    const payload = await response.json().catch(() => undefined);
    if (!response.ok) {
      const message = payload?.error?.message ?? `Request failed with ${response.status}`;
      throw new Error(message);
    }
    return payload as T;
  }
}
