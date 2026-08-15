import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useAppData } from "../state/app-data";
import { Card, PageHeader, StatCard, StatusPill } from "../shared-ui";
import type { AgentRunDetail, CampaignCreateInput, LeadSeedInput, ToolCall } from "../types/domain";
import type { Screen } from "../types/navigation";
import { formatDate } from "../utils/format";
import { statusTone } from "../utils/status";

type CampaignDraft = {
  name: string;
  maxLeads: string;
  channel: "email" | "linkedin" | "manual" | "phone";
  goalOverride: string;
  seedLeads: string;
};

const defaultCampaignDraft: CampaignDraft = {
  name: "",
  maxLeads: "25",
  channel: "email",
  goalOverride: "",
  seedLeads: "",
};

export function CampaignsScreen({ onNavigate }: { onNavigate: (screen: Screen) => void }) {
  const {
    selectedProductId,
    selectedProduct,
    productCampaigns,
    selectedCampaignId,
    snapshot,
    createCampaign,
    deleteCampaigns,
    setSelectedCampaignId,
    runCampaign,
    pauseCampaign,
    resumeCampaign,
    enqueueCampaign,
  } = useAppData();
  const [showNewCampaign, setShowNewCampaign] = useState(false);
  const [draft, setDraft] = useState<CampaignDraft>(defaultCampaignDraft);
  const [selectedCampaignIds, setSelectedCampaignIds] = useState<string[]>([]);
  const metrics = snapshot.metrics;
  const parsedMaxLeads = Number.parseInt(draft.maxLeads, 10);
  const canCreateCampaign =
    Boolean(selectedProductId) &&
    draft.name.trim().length > 0 &&
    Number.isInteger(parsedMaxLeads) &&
    parsedMaxLeads > 0 &&
    parsedMaxLeads <= 1000;
  const runningCampaigns = productCampaigns.filter((campaign) =>
    ["discovering", "researching", "qualifying", "drafting_outreach", "sending"].includes(
      campaign.status,
    ),
  );
  const awaitingApprovalCampaigns = productCampaigns.filter(
    (campaign) => campaign.status === "awaiting_approval",
  );
  const allVisibleSelected =
    productCampaigns.length > 0 &&
    productCampaigns.every((campaign) => selectedCampaignIds.includes(campaign.id));
  const defaultCampaignName = useMemo(() => {
    const date = new Date().toISOString().slice(0, 10);
    return selectedProduct ? `${selectedProduct.product_name} validation ${date}` : `Campaign ${date}`;
  }, [selectedProduct]);

  const openNewCampaign = () => {
    setDraft({ ...defaultCampaignDraft, name: defaultCampaignName });
    setShowNewCampaign(true);
  };

  const updateDraft = (field: keyof CampaignDraft, value: string) => {
    setDraft((current) => ({ ...current, [field]: value }));
  };

  const submitCampaign = async () => {
    if (!selectedProductId || !canCreateCampaign) return;
    const input: CampaignCreateInput = {
      product_id: selectedProductId,
      name: draft.name.trim(),
      max_leads: parsedMaxLeads,
      channels: [draft.channel],
      discovery_seeds: parseSeedLeads(draft.seedLeads),
      goal_override: draft.goalOverride.trim() || null,
    };
    const created = await createCampaign(input);
    if (created) {
      setShowNewCampaign(false);
      setDraft(defaultCampaignDraft);
    }
  };

  const toggleSelectedCampaign = (campaignId: string) => {
    setSelectedCampaignIds((current) =>
      current.includes(campaignId)
        ? current.filter((id) => id !== campaignId)
        : [...current, campaignId],
    );
  };

  const toggleAllVisibleCampaigns = () => {
    setSelectedCampaignIds(allVisibleSelected ? [] : productCampaigns.map((campaign) => campaign.id));
  };

  const deleteSelectedCampaigns = async () => {
    if (selectedCampaignIds.length === 0) return;
    const confirmed = window.confirm(
      `Delete ${selectedCampaignIds.length} campaign${selectedCampaignIds.length === 1 ? "" : "s"} and related workflow records?`,
    );
    if (!confirmed) return;
    await deleteCampaigns(selectedCampaignIds);
    setSelectedCampaignIds([]);
  };

  return (
    <>
      <PageHeader
        title="Campaigns"
        subtitle="Repeatable discovery + outreach runs against your ICP."
        actions={
          <button disabled={!selectedProductId} onClick={openNewCampaign}>
            <Plus size={14} />
            New campaign
          </button>
        }
      />

      {showNewCampaign ? (
        <div className="campaign-setup">
          <Card title="New campaign" meta={<StatusPill tone="blue">Draft</StatusPill>}>
            <div className="form-grid two">
              <label className="field">
                <span>Campaign name</span>
                <input
                  value={draft.name}
                  onChange={(event) => updateDraft("name", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Max leads</span>
                <input
                  inputMode="numeric"
                  min="1"
                  max="1000"
                  type="number"
                  value={draft.maxLeads}
                  onChange={(event) => updateDraft("maxLeads", event.target.value)}
                />
              </label>
            </div>
            <div className="form-grid two">
              <label className="field">
                <span>Primary channel</span>
                <select
                  value={draft.channel}
                  onChange={(event) => updateDraft("channel", event.target.value as CampaignDraft["channel"])}
                >
                  <option value="email">Email</option>
                  <option value="linkedin">LinkedIn</option>
                  <option value="manual">Manual</option>
                  <option value="phone">Phone</option>
                </select>
              </label>
              <label className="field">
                <span>Goal override</span>
                <input
                  placeholder={selectedProduct?.validation_goal || "Optional"}
                  value={draft.goalOverride}
                  onChange={(event) => updateDraft("goalOverride", event.target.value)}
                />
              </label>
            </div>
            <label className="field">
              <span>Seed leads</span>
              <textarea
                rows={4}
                placeholder="Company | website | email | geography | notes"
                value={draft.seedLeads}
                onChange={(event) => updateDraft("seedLeads", event.target.value)}
              />
              <em>Optional. One lead per line.</em>
            </label>
            {!canCreateCampaign ? (
              <p className="field-help product-form-help">
                Add a campaign name and use a max lead count from 1 to 1000.
              </p>
            ) : null}
            <div className="form-actions">
              <button className="secondary" onClick={() => setShowNewCampaign(false)}>
                Cancel
              </button>
              <button disabled={!canCreateCampaign} onClick={submitCampaign}>
                Create campaign
              </button>
            </div>
          </Card>
        </div>
      ) : null}

      <div className="stat-grid four">
        <StatCard label="Running campaigns" value={String(runningCampaigns.length)} />
        <StatCard label="Awaiting approval" value={String(awaitingApprovalCampaigns.length)} />
        <StatCard label="Sent" value={String(metrics?.sent_count ?? 0)} />
        <StatCard label="Interviews requested" value={String(metrics?.interview_request_count ?? 0)} />
      </div>

      <Card
        title="Selected product campaigns"
        meta={
          <div className="card-actions">
            {selectedCampaignIds.length > 0 ? (
              <button className="danger" onClick={deleteSelectedCampaigns}>
                Delete selected
              </button>
            ) : null}
            <span className="muted">{productCampaigns.length} total</span>
          </div>
        }
      >
        {productCampaigns.length === 0 ? (
          <p className="empty-copy">Create a campaign for the selected product.</p>
        ) : (
          <div className="table-shell bare">
            <table className="data-table campaigns-table">
              <thead>
                <tr>
                  <th className="selection-cell">
                    <input
                      aria-label="Select all campaigns"
                      checked={allVisibleSelected}
                      type="checkbox"
                      onChange={toggleAllVisibleCampaigns}
                    />
                  </th>
                  <th>Campaign</th>
                  <th>Status</th>
                  <th>Stage</th>
                  <th>Max leads</th>
                  <th>Sent</th>
                  <th>Replies</th>
                  <th>Started</th>
                  <th>Controls</th>
                </tr>
              </thead>
              <tbody>
                {productCampaigns.map((campaign) => {
                  const selected = selectedCampaignId === campaign.id;
                  const selectedMetrics = selected ? metrics : undefined;
                  return (
                    <tr
                      className={selected ? "selected-row" : ""}
                      key={campaign.id}
                      onClick={() => setSelectedCampaignId(campaign.id)}
                    >
                      <td className="selection-cell">
                        <input
                          aria-label={`Select ${campaign.name || campaign.id}`}
                          checked={selectedCampaignIds.includes(campaign.id)}
                          type="checkbox"
                          onChange={() => toggleSelectedCampaign(campaign.id)}
                          onClick={(event) => event.stopPropagation()}
                        />
                      </td>
                      <td>
                        <strong>{campaign.name || "Untitled campaign"}</strong>
                        <span>{campaign.id}</span>
                      </td>
                      <td>
                        <StatusPill tone={statusTone(campaign.status)}>{campaign.status}</StatusPill>
                      </td>
                      <td>{campaign.stage}</td>
                      <td>{campaign.max_leads}</td>
                      <td>{selectedMetrics?.sent_count ?? "-"}</td>
                      <td>{selectedMetrics?.response_count ?? "-"}</td>
                      <td>
                        <span>{formatDate(campaign.created_at)}</span>
                      </td>
                      <td>
                        <CampaignControl
                          status={campaign.status}
                          onRun={() => runCampaign(campaign.id)}
                          onQueue={() => enqueueCampaign(campaign.id)}
                          onPause={() => pauseCampaign(campaign.id)}
                          onResume={() => resumeCampaign(campaign.id)}
                          onReview={() => onNavigate("approvals")}
                          onViewLeads={() => onNavigate("leads")}
                          onViewConversations={() => onNavigate("conversations")}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {selectedCampaignId ? (
        <AgentRunPanel run={snapshot.latestAgentRun} totalRuns={snapshot.agentRuns.length} />
      ) : null}
    </>
  );
}

function AgentRunPanel({ run, totalRuns }: { run?: AgentRunDetail; totalRuns: number }) {
  return (
    <Card
      title="Latest agent run"
      meta={
        run ? (
          <div className="card-actions">
            <StatusPill tone={statusTone(run.status)}>{run.status}</StatusPill>
            <span className="muted">{totalRuns} total</span>
          </div>
        ) : undefined
      }
    >
      {!run ? (
        <p className="empty-copy">No agent run has been recorded for the selected campaign.</p>
      ) : (
        <div className="agent-run-panel">
          <div className="agent-run-summary">
            <div>
              <span>Objective</span>
              <strong>{run.objective}</strong>
            </div>
            <div>
              <span>Current phase</span>
              <strong>{run.current_phase || "none"}</strong>
            </div>
            <div>
              <span>Tool calls</span>
              <strong>
                {run.tool_call_count} / {run.max_tool_calls}
              </strong>
            </div>
          </div>
          {run.error ? <p className="run-error">{run.error}</p> : null}
          <div className="agent-run-columns">
            <div>
              <h3>Steps</h3>
              {run.steps.length === 0 ? (
                <p className="empty-copy">No workflow steps have started yet.</p>
              ) : (
                <ul className="agent-step-list">
                  {run.steps.map((step) => (
                    <li key={step.id}>
                      <div>
                        <strong>{step.phase}</strong>
                        <span>{step.objective}</span>
                      </div>
                      <span>{snapshotCount(step.output_snapshot)}</span>
                      <StatusPill tone={statusTone(step.status)}>{step.status}</StatusPill>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h3>Tool calls</h3>
              {run.tool_calls.length === 0 ? (
                <p className="empty-copy">No tool calls have been recorded yet.</p>
              ) : (
                <ul className="agent-tool-list">
                  {run.tool_calls.map((toolCall) => (
                    <li key={toolCall.id}>
                      <div>
                        <strong>{toolCall.tool_name}</strong>
                        <span>{toolCall.reason || "No reason recorded"}</span>
                      </div>
                      <span>{toolObservationLabel(toolCall)}</span>
                      <StatusPill tone={statusTone(toolCall.status)}>{toolCall.status}</StatusPill>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

function toolObservationLabel(toolCall: ToolCall): string {
  if (Array.isArray(toolCall.observation)) return `${toolCall.observation.length} results`;
  if (typeof toolCall.observation === "string") return toolCall.observation.slice(0, 32);
  if (toolCall.observation && "count" in toolCall.observation) {
    return `${String(toolCall.observation.count)} results`;
  }
  return toolCall.status;
}

function snapshotCount(snapshot?: Record<string, unknown> | null): string {
  if (!snapshot || !("count" in snapshot)) return "-";
  return String(snapshot.count);
}

function parseSeedLeads(value: string): LeadSeedInput[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [companyName, websiteUrl, contactEmail, geography, ...descriptionParts] = line
        .split("|")
        .map((part) => part.trim());
      return {
        company_name: companyName,
        website_url: websiteUrl || null,
        contact_email: contactEmail || null,
        geography: geography || null,
        description: descriptionParts.join(" | ") || null,
        source: "manual",
      };
    })
    .filter((seed) => seed.company_name.length > 0);
}

function CampaignControl({
  status,
  onRun,
  onQueue,
  onPause,
  onResume,
  onReview,
  onViewLeads,
  onViewConversations,
}: {
  status: string;
  onRun: () => void;
  onQueue: () => void;
  onPause: () => void;
  onResume: () => void;
  onReview: () => void;
  onViewLeads: () => void;
  onViewConversations: () => void;
}) {
  if (status === "paused") {
    return <button onClick={(event) => { event.stopPropagation(); onResume(); }}>Resume</button>;
  }
  if (status === "draft") {
    return <button onClick={(event) => { event.stopPropagation(); onRun(); }}>Run</button>;
  }
  if (status === "failed") {
    return <button className="secondary" disabled onClick={(event) => event.stopPropagation()}>Failed</button>;
  }
  if (status === "awaiting_approval") {
    return <button onClick={(event) => { event.stopPropagation(); onReview(); }}>Review</button>;
  }
  if (status === "tracking") {
    return <button className="secondary" onClick={(event) => { event.stopPropagation(); onViewConversations(); }}>Conversations</button>;
  }
  if (status === "completed") {
    return <button className="secondary" onClick={(event) => { event.stopPropagation(); onViewLeads(); }}>Results</button>;
  }
  if (["discovering", "researching", "qualifying", "drafting_outreach", "sending"].includes(status)) {
    return <button className="secondary" onClick={(event) => { event.stopPropagation(); onPause(); }}>Pause</button>;
  }
  return <button className="secondary" onClick={(event) => { event.stopPropagation(); onQueue(); }}>Queue</button>;
}
