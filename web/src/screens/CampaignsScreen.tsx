import { Plus } from "lucide-react";
import { useAppData } from "../state/app-data";
import { Card, PageHeader, StatCard, StatusPill } from "../shared-ui";
import { formatDate } from "../utils/format";
import { statusTone } from "../utils/status";

export function CampaignsScreen() {
  const {
    productCampaigns,
    selectedCampaignId,
    snapshot,
    createCampaign,
    setSelectedCampaignId,
    runCampaign,
    pauseCampaign,
    resumeCampaign,
    enqueueCampaign,
  } = useAppData();
  const metrics = snapshot.metrics;
  const activeCampaigns = productCampaigns.filter((campaign) =>
    ["discovering", "researching", "qualifying", "drafting_outreach", "awaiting_approval", "sending", "tracking"].includes(
      campaign.status,
    ),
  );

  return (
    <>
      <PageHeader
        title="Campaigns"
        subtitle="Repeatable discovery + outreach runs against your ICP."
        actions={
          <button onClick={createCampaign}>
            <Plus size={14} />
            New campaign
          </button>
        }
      />

      <div className="stat-grid four">
        <StatCard label="Active campaigns" value={String(activeCampaigns.length)} />
        <StatCard label="In queue for approval" value={String(metrics?.pending_approval_count ?? 0)} />
        <StatCard label="Sent" value={String(metrics?.sent_count ?? 0)} />
        <StatCard label="Interviews requested" value={String(metrics?.interview_request_count ?? 0)} />
      </div>

      <Card title="All campaigns" meta={<span className="muted">{productCampaigns.length} total</span>}>
        {productCampaigns.length === 0 ? (
          <p className="empty-copy">Create a campaign for the selected product.</p>
        ) : (
          <div className="table-shell bare">
            <table className="data-table">
              <thead>
                <tr>
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
    </>
  );
}

function CampaignControl({
  status,
  onRun,
  onQueue,
  onPause,
  onResume,
}: {
  status: string;
  onRun: () => void;
  onQueue: () => void;
  onPause: () => void;
  onResume: () => void;
}) {
  if (status === "paused") {
    return <button onClick={(event) => { event.stopPropagation(); onResume(); }}>Resume</button>;
  }
  if (status === "draft" || status === "failed") {
    return <button onClick={(event) => { event.stopPropagation(); onRun(); }}>Run</button>;
  }
  if (status === "completed") {
    return <button className="secondary" onClick={(event) => { event.stopPropagation(); onQueue(); }}>Queue</button>;
  }
  return <button className="secondary" onClick={(event) => { event.stopPropagation(); onPause(); }}>Pause</button>;
}
