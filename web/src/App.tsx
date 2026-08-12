import {
  Check,
  Edit3,
  Pause,
  Play,
  Plus,
  RefreshCcw,
  Send,
  Trash2,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClient, Campaign, CampaignSnapshot, Message, Product } from "./api";

const defaultProductJson = JSON.stringify(
  {
    product_name: "QuoteVan",
    product_description: "Quoting workflow software for residential painters.",
    target_customer: "Residential painters",
    problem_being_solved: "Painters lose time and deals when quote follow-up is slow.",
    value_proposition: "Create polished painting quotes and follow-ups faster.",
    target_geography: "Ontario, Canada",
    validation_goal: "Book 10 customer discovery interviews.",
    qualification_criteria: [
      { label: "Residential painting services", weight: 3, required: true },
      { label: "Visible contact information", weight: 2 },
      { label: "Serves homeowners", weight: 2 },
    ],
    preferred_discovery_sources: [
      {
        type: "seed",
        value:
          "Maple House Painters|https://example.com|Residential painting company serving homeowners in Ontario|Ontario, Canada|hello@example.com",
      },
    ],
    outreach_objective: "Ask for a 20-minute customer discovery interview.",
    constraints: ["Human approval is required before sending."],
  },
  null,
  2,
);

const defaultSeedJson = JSON.stringify(
  [
    {
      company_name: "Maple House Painters",
      website_url: "https://example.com",
      contact_email: "hello@example.com",
      geography: "Ontario, Canada",
      description: "Residential painting company serving homeowners.",
    },
  ],
  null,
  2,
);

export function App() {
  const [apiBaseUrl, setApiBaseUrl] = useState(
    localStorage.getItem("apiBaseUrl") || import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
  );
  const [apiToken, setApiToken] = useState(
    localStorage.getItem("apiToken") || import.meta.env.VITE_API_TOKEN || "",
  );
  const [products, setProducts] = useState<Product[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedProductId, setSelectedProductId] = useState("");
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [productJson, setProductJson] = useState(defaultProductJson);
  const [seedJson, setSeedJson] = useState(defaultSeedJson);
  const [maxLeads, setMaxLeads] = useState(25);
  const [snapshot, setSnapshot] = useState<CampaignSnapshot>({
    leads: [],
    messages: [],
    conversations: [],
  });
  const [editing, setEditing] = useState<Record<string, Pick<Message, "subject" | "body" | "approach_tag">>>({});
  const [responseDrafts, setResponseDrafts] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("Idle");
  const [error, setError] = useState("");

  const api = useMemo(() => new ApiClient({ baseUrl: apiBaseUrl, token: apiToken }), [apiBaseUrl, apiToken]);

  const run = useCallback(async (label: string, action: () => Promise<unknown>) => {
    setError("");
    setStatus(label);
    try {
      await action();
      setStatus("Ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("Blocked");
    }
  }, []);

  const loadCore = useCallback(async () => {
    const [nextProducts, nextCampaigns] = await Promise.all([api.getProducts(), api.getCampaigns()]);
    setProducts(nextProducts);
    setCampaigns(nextCampaigns);
    setSelectedProductId((current) => current || nextProducts[0]?.id || "");
    setSelectedCampaignId((current) => current || nextCampaigns[0]?.id || "");
  }, [api]);

  const loadCampaign = useCallback(
    async (campaignId: string) => {
      if (!campaignId) return;
      const [campaign, leads, messages, conversations, metrics] = await Promise.all([
        api.getCampaign(campaignId),
        api.getLeads(campaignId),
        api.getMessages(campaignId),
        api.getConversations(campaignId),
        api.getMetrics(campaignId),
      ]);
      setSnapshot({ campaign, leads, messages, conversations, metrics });
      setEditing(
        Object.fromEntries(
          messages.map((message) => [
            message.id,
            {
              subject: message.subject,
              body: message.body,
              approach_tag: message.approach_tag,
            },
          ]),
        ),
      );
    },
    [api],
  );

  useEffect(() => {
    localStorage.setItem("apiBaseUrl", apiBaseUrl);
    localStorage.setItem("apiToken", apiToken);
  }, [apiBaseUrl, apiToken]);

  useEffect(() => {
    run("Loading", loadCore);
  }, [loadCore, run]);

  useEffect(() => {
    if (selectedCampaignId) {
      run("Loading campaign", () => loadCampaign(selectedCampaignId));
    }
  }, [selectedCampaignId, loadCampaign, run]);

  const createProduct = () =>
    run("Creating product", async () => {
      const product = await api.createProduct(JSON.parse(productJson));
      await loadCore();
      setSelectedProductId(product.id);
    });

  const createCampaign = () =>
    run("Creating campaign", async () => {
      const campaign = await api.createCampaign({
        product_id: selectedProductId,
        max_leads: maxLeads,
        channels: ["email"],
      });
      await loadCore();
      setSelectedCampaignId(campaign.id);
    });

  const refreshSelectedCampaign = () => run("Refreshing", () => loadCampaign(selectedCampaignId));

  const mutateCampaign = (label: string, action: () => Promise<unknown>) =>
    run(label, async () => {
      await action();
      await loadCore();
      await loadCampaign(selectedCampaignId);
    });

  const saveMessage = (messageId: string) =>
    mutateCampaign("Saving draft", () => api.updateMessage(messageId, editing[messageId]));

  const selectedCampaign = snapshot.campaign ?? campaigns.find((campaign) => campaign.id === selectedCampaignId);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>scoutlead</h1>
          <p>{status}</p>
        </div>
        <div className="connection">
          <input value={apiBaseUrl} onChange={(event) => setApiBaseUrl(event.target.value)} />
          <input
            value={apiToken}
            onChange={(event) => setApiToken(event.target.value)}
            placeholder="API token"
            type="password"
          />
          <button title="Refresh data" onClick={() => run("Refreshing", loadCore)}>
            <RefreshCcw size={16} />
          </button>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <section className="layout">
        <aside className="sidebar">
          <section className="panel">
            <div className="panel-title">
              <h2>Products</h2>
              <button title="Create product" onClick={createProduct}>
                <Plus size={16} />
              </button>
            </div>
            <textarea value={productJson} onChange={(event) => setProductJson(event.target.value)} rows={15} />
            <select value={selectedProductId} onChange={(event) => setSelectedProductId(event.target.value)}>
              <option value="">Select product</option>
              {products.map((product) => (
                <option value={product.id} key={product.id}>
                  {product.product_name}
                </option>
              ))}
            </select>
          </section>

          <section className="panel">
            <div className="panel-title">
              <h2>Campaigns</h2>
              <button title="Create campaign" disabled={!selectedProductId} onClick={createCampaign}>
                <Plus size={16} />
              </button>
            </div>
            <div className="form-row">
              <label>Max leads</label>
              <input
                type="number"
                value={maxLeads}
                min={1}
                max={1000}
                onChange={(event) => setMaxLeads(Number(event.target.value))}
              />
            </div>
            <select value={selectedCampaignId} onChange={(event) => setSelectedCampaignId(event.target.value)}>
              <option value="">Select campaign</option>
              {campaigns.map((campaign) => (
                <option value={campaign.id} key={campaign.id}>
                  {campaign.name || campaign.id} · {campaign.status}
                </option>
              ))}
            </select>
            <div className="button-grid">
              <button title="Run campaign" disabled={!selectedCampaignId} onClick={() => mutateCampaign("Running campaign", () => api.runCampaign(selectedCampaignId))}>
                <Play size={16} />
                Run
              </button>
              <button title="Pause campaign" disabled={!selectedCampaignId} onClick={() => mutateCampaign("Pausing campaign", () => api.pauseCampaign(selectedCampaignId))}>
                <Pause size={16} />
                Pause
              </button>
              <button title="Resume campaign" disabled={!selectedCampaignId} onClick={() => mutateCampaign("Resuming campaign", () => api.resumeCampaign(selectedCampaignId))}>
                <Play size={16} />
                Resume
              </button>
              <button title="Queue campaign" disabled={!selectedCampaignId} onClick={() => mutateCampaign("Queueing campaign", () => api.enqueueCampaign(selectedCampaignId))}>
                <Upload size={16} />
                Queue
              </button>
            </div>
          </section>

          <section className="panel">
            <div className="panel-title">
              <h2>Seed Leads</h2>
              <button
                title="Add seed leads"
                disabled={!selectedCampaignId}
                onClick={() =>
                  mutateCampaign("Adding seed leads", () =>
                    api.addSeedLeads(selectedCampaignId, JSON.parse(seedJson)),
                  )
                }
              >
                <Plus size={16} />
              </button>
            </div>
            <textarea value={seedJson} onChange={(event) => setSeedJson(event.target.value)} rows={10} />
          </section>
        </aside>

        <section className="workspace">
          <section className="summary-strip">
            <Metric label="Campaign" value={selectedCampaign?.status || "none"} />
            <Metric label="Leads" value={snapshot.metrics?.lead_count ?? 0} />
            <Metric label="Qualified" value={snapshot.metrics?.qualified_lead_count ?? 0} />
            <Metric label="Pending" value={snapshot.metrics?.pending_approval_count ?? 0} />
            <Metric label="Sent" value={snapshot.metrics?.sent_count ?? 0} />
            <Metric label="Responses" value={snapshot.metrics?.response_count ?? 0} />
            <button title="Refresh campaign" disabled={!selectedCampaignId} onClick={refreshSelectedCampaign}>
              <RefreshCcw size={16} />
            </button>
          </section>

          <section className="panel">
            <h2>Leads</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Status</th>
                    <th>Score</th>
                    <th>Email</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshot.leads.map((lead) => (
                    <tr key={lead.id}>
                      <td>
                        <strong>{lead.company_name}</strong>
                        <span>{lead.website_url}</span>
                      </td>
                      <td>{lead.status}</td>
                      <td>{lead.qualification?.score ?? lead.research?.confidence ?? "—"}</td>
                      <td>{lead.contact_email || "—"}</td>
                      <td>{lead.qualification?.rationale || lead.research?.summary || lead.description || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <h2>Outreach Review</h2>
            <div className="message-list">
              {snapshot.messages.map((message) => (
                <article className="message-row" key={message.id}>
                  <div className="message-meta">
                    <span>{message.status}</span>
                    <span>{message.approach_tag}</span>
                    <span>{snapshot.leads.find((lead) => lead.id === message.lead_id)?.company_name}</span>
                  </div>
                  <input
                    value={editing[message.id]?.subject || ""}
                    onChange={(event) =>
                      setEditing((current) => ({
                        ...current,
                        [message.id]: { ...current[message.id], subject: event.target.value },
                      }))
                    }
                  />
                  <textarea
                    rows={7}
                    value={editing[message.id]?.body || ""}
                    onChange={(event) =>
                      setEditing((current) => ({
                        ...current,
                        [message.id]: { ...current[message.id], body: event.target.value },
                      }))
                    }
                  />
                  <div className="action-row">
                    <button title="Save draft" onClick={() => saveMessage(message.id)}>
                      <Edit3 size={16} />
                      Save
                    </button>
                    <button title="Approve draft" onClick={() => mutateCampaign("Approving", () => api.approveMessage(message.id, "operator"))}>
                      <Check size={16} />
                      Approve
                    </button>
                    <button title="Send approved message" onClick={() => mutateCampaign("Sending", () => api.sendMessage(message.id))}>
                      <Send size={16} />
                      Send
                    </button>
                    <button title="Cancel draft" onClick={() => mutateCampaign("Canceling", () => api.cancelMessage(message.id))}>
                      <Trash2 size={16} />
                      Cancel
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="panel">
            <h2>Conversations</h2>
            <div className="conversation-list">
              {snapshot.conversations.map((conversation) => (
                <article className="conversation-row" key={conversation.id}>
                  <div className="message-meta">
                    <span>{conversation.status}</span>
                    <span>{snapshot.leads.find((lead) => lead.id === conversation.lead_id)?.company_name}</span>
                  </div>
                  <div className="events">
                    {conversation.events.map((event) => (
                      <p key={event.id}>
                        <strong>{event.direction}</strong> {event.body}
                        {event.classification && (
                          <span>
                            {event.classification.intent} · {event.classification.follow_up_action}
                          </span>
                        )}
                      </p>
                    ))}
                  </div>
                  <textarea
                    rows={3}
                    value={responseDrafts[conversation.id] || ""}
                    onChange={(event) =>
                      setResponseDrafts((current) => ({
                        ...current,
                        [conversation.id]: event.target.value,
                      }))
                    }
                  />
                  <button
                    title="Record response"
                    onClick={() =>
                      mutateCampaign("Classifying response", () =>
                        api.recordResponse(conversation.id, responseDrafts[conversation.id] || ""),
                      )
                    }
                  >
                    <Plus size={16} />
                    Response
                  </button>
                </article>
              ))}
            </div>
          </section>

          <section className="panel">
            <h2>Approach Performance</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Approach</th>
                    <th>Sent</th>
                    <th>Replies</th>
                    <th>Positive</th>
                    <th>Response rate</th>
                  </tr>
                </thead>
                <tbody>
                  {(snapshot.metrics?.approach_performance || []).map((approach) => (
                    <tr key={approach.approach_tag}>
                      <td>{approach.approach_tag}</td>
                      <td>{approach.sent}</td>
                      <td>{approach.replies}</td>
                      <td>{approach.positive_replies}</td>
                      <td>{Math.round(approach.response_rate * 100)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </section>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
