import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useAppData } from "../state/app-data";
import { Card, PageHeader, StatCard, StatusPill } from "../shared-ui";
import type {
  AgentRunDetail,
  CampaignCreateInput,
  CampaignPreflight,
  ToolCall,
} from "../types/domain";
import type { Screen } from "../types/navigation";
import { formatDate } from "../utils/format";
import { statusTone } from "../utils/status";

type CampaignDraft = {
  source: string;
};

const defaultCampaignDraft: CampaignDraft = {
  source: "",
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
    updateSelectedProduct,
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
  const canCreateCampaign = Boolean(selectedProductId);
  const runningCampaigns = productCampaigns.filter((campaign) =>
    ["discovering", "researching", "qualifying", "drafting_outreach", "sending"].includes(
      campaign.status,
    ),
  );
  const awaitingApprovalCampaigns = productCampaigns.filter(
    (campaign) => campaign.status === "awaiting_approval",
  );
  const preflight = snapshot.preflight;
  const allVisibleSelected =
    productCampaigns.length > 0 &&
    productCampaigns.every((campaign) => selectedCampaignIds.includes(campaign.id));
  const defaultCampaignName = useMemo(() => {
    const date = new Date().toISOString().slice(0, 10);
    return selectedProduct ? `${selectedProduct.product_name} validation ${date}` : `Campaign ${date}`;
  }, [selectedProduct]);

  const openNewCampaign = () => {
    setDraft(defaultCampaignDraft);
    setShowNewCampaign(true);
  };

  const updateDraft = (field: keyof CampaignDraft, value: string) => {
    setDraft((current) => ({ ...current, [field]: value }));
  };

  const submitCampaign = async () => {
    if (!selectedProductId || !canCreateCampaign) return;
    const source = draft.source.trim();
    if (selectedProduct && source) {
      await updateSelectedProduct({
        preferred_discovery_sources: [{ type: "web_search", value: source, limit: 10 }],
      });
    }
    const input: CampaignCreateInput = {
      product_id: selectedProductId,
      name: defaultCampaignName,
      max_leads: 10,
      channels: ["email"],
      discovery_seeds: [],
      goal_override: null,
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
            <div className="source-create">
              <label className="field">
                <span>Discovery source</span>
                <input
                  autoFocus
                  placeholder="residential painters Austin Texas or https://directory.example"
                  value={draft.source}
                  onChange={(event) => updateDraft("source", event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void submitCampaign();
                  }}
                />
                <em>Blank uses the selected product discovery profile.</em>
              </label>
              <button disabled={!canCreateCampaign} onClick={submitCampaign}>
                Create campaign
              </button>
              <button className="secondary" onClick={() => setShowNewCampaign(false)}>
                Cancel
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
                          preflightReady={campaign.id === selectedCampaignId && preflight ? preflight.ready : true}
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
        <>
          <PreflightPanel preflight={preflight} />
          <AgentRunPanel run={snapshot.latestAgentRun} totalRuns={snapshot.agentRuns.length} />
        </>
      ) : null}
    </>
  );
}

function PreflightPanel({ preflight }: { preflight?: CampaignPreflight }) {
  if (!preflight) return null;
  return (
    <Card
      title="Run preflight"
      meta={<StatusPill tone={preflight.ready ? "green" : "red"}>{preflight.ready ? "Ready" : "Blocked"}</StatusPill>}
    >
      <ul className="preflight-list">
        {preflight.checks.map((check) => (
          <li key={check.name}>
            <div>
              <strong>{check.name}</strong>
              <span>{check.detail}</span>
            </div>
            <StatusPill tone={statusTone(check.status)}>{check.status}</StatusPill>
          </li>
        ))}
      </ul>
    </Card>
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

function CampaignControl({
  status,
  preflightReady,
  onRun,
  onQueue,
  onPause,
  onResume,
  onReview,
  onViewLeads,
  onViewConversations,
}: {
  status: string;
  preflightReady: boolean;
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
    return <button disabled={!preflightReady} onClick={(event) => { event.stopPropagation(); onRun(); }}>Run</button>;
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
