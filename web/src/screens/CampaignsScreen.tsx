import { useState } from "react";
import { useAppData } from "../state/app-data";
import { Card, StatCard, StatusPill } from "../shared-ui";
import type { Campaign, Metrics } from "../types/domain";
import type { Screen } from "../types/navigation";
import { formatDate } from "../utils/format";
import { statusTone } from "../utils/status";

export function CampaignsScreen({ onNavigate }: { onNavigate: (screen: Screen) => void }) {
  const {
    productCampaigns,
    selectedCampaignId,
    snapshot,
    deleteCampaigns,
    setSelectedCampaignId,
    runCampaign,
    pauseCampaign,
    resumeCampaign,
    enqueueCampaign,
  } = useAppData();
  const [selectedCampaignIds, setSelectedCampaignIds] = useState<string[]>([]);
  const metrics = snapshot.metrics;
  const runningCampaigns = productCampaigns.filter((campaign) =>
    ["discovering", "researching", "qualifying", "drafting_outreach", "sending"].includes(
      campaign.status,
    ),
  );
  const awaitingApprovalCampaigns = productCampaigns.filter(
    (campaign) => campaign.status === "awaiting_approval",
  );
  const preflight = snapshot.preflight;
  const selectedCampaign = snapshot.campaign ?? productCampaigns.find((campaign) => campaign.id === selectedCampaignId);
  const allVisibleSelected =
    productCampaigns.length > 0 &&
    productCampaigns.every((campaign) => selectedCampaignIds.includes(campaign.id));

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
      <div className="stat-grid four">
        <StatCard label="Running campaigns" value={String(runningCampaigns.length)} />
        <StatCard label="Needs review" value={String(awaitingApprovalCampaigns.length)} />
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
                  <th>Leads</th>
                  <th>Review</th>
                  <th>Sent</th>
                  <th>Replies</th>
                  <th>Started</th>
                  <th>Action</th>
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
                      <td>{selectedMetrics?.lead_count ?? "-"}</td>
                      <td>{selectedMetrics?.pending_approval_count ?? "-"}</td>
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
        <SelectedCampaignSummary
          campaign={selectedCampaign}
          metrics={metrics}
          preflightReady={preflight?.ready ?? true}
          onRun={() => runCampaign(selectedCampaignId)}
          onReview={() => onNavigate("approvals")}
          onViewLeads={() => onNavigate("leads")}
        />
      ) : null}
    </>
  );
}

function SelectedCampaignSummary({
  campaign,
  metrics,
  preflightReady,
  onRun,
  onReview,
  onViewLeads,
}: {
  campaign?: Campaign;
  metrics?: Metrics;
  preflightReady: boolean;
  onRun: () => void;
  onReview: () => void;
  onViewLeads: () => void;
}) {
  if (!campaign) return null;
  const needsReview = metrics?.pending_approval_count ?? 0;
  return (
    <Card
      title="Selected campaign"
      meta={
        <StatusPill tone={statusTone(campaign.status)}>{campaign.status}</StatusPill>
      }
    >
      <div className="campaign-summary">
        <div>
          <span>Campaign</span>
          <strong>{campaign.name}</strong>
        </div>
        <div>
          <span>Leads</span>
          <strong>{metrics?.lead_count ?? 0}</strong>
        </div>
        <div>
          <span>Qualified</span>
          <strong>{metrics?.qualified_lead_count ?? 0}</strong>
        </div>
        <div>
          <span>Needs review</span>
          <strong>{needsReview}</strong>
        </div>
        <div>
          <span>Replies</span>
          <strong>{metrics?.response_count ?? 0}</strong>
        </div>
      </div>
      <div className="form-actions">
        {campaign.status === "draft" || campaign.status === "paused" ? (
          <button disabled={!preflightReady} onClick={onRun}>Run campaign</button>
        ) : null}
        {needsReview > 0 || campaign.status === "awaiting_approval" ? (
          <button onClick={onReview}>Review outreach</button>
        ) : null}
        <button className="secondary" onClick={onViewLeads}>View leads</button>
        {!preflightReady ? (
          <span className="muted">Missing required setup before this campaign can run.</span>
        ) : null}
      </div>
    </Card>
  );
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
