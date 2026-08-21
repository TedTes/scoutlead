import { useAppData } from "../state/app-data";
import { Card, StatCard, StatusPill } from "../shared-ui";
import type { Tone } from "../types/navigation";
import { formatPercent } from "../utils/format";
import { statusTone } from "../utils/status";

export function OverviewScreen() {
  const { selectedDiscoveryRun: selectedRun, snapshot } = useAppData();
  const metrics = snapshot.metrics;
  const funnel = [
    { label: "Sourced", value: metrics?.lead_count ?? 0, pct: "100%", width: 100, tone: "gray" as Tone },
    {
      label: "Researched",
      value: metrics?.researched_lead_count ?? 0,
      pct: metrics?.lead_count ? formatPercent((metrics.researched_lead_count ?? 0) / metrics.lead_count) : "0%",
      width: metrics?.lead_count ? Math.round((metrics.researched_lead_count / metrics.lead_count) * 100) : 0,
      tone: "blue" as Tone,
    },
    {
      label: "Qualified",
      value: metrics?.qualified_lead_count ?? 0,
      pct: metrics?.lead_count ? formatPercent((metrics.qualified_lead_count ?? 0) / metrics.lead_count) : "0%",
      width: metrics?.lead_count ? Math.round((metrics.qualified_lead_count / metrics.lead_count) * 100) : 0,
      tone: "blue" as Tone,
    },
    {
      label: "Approved",
      value: approvedCount(snapshot.messages),
      pct: metrics?.lead_count ? formatPercent(approvedCount(snapshot.messages) / metrics.lead_count) : "0%",
      width: metrics?.lead_count ? Math.round((approvedCount(snapshot.messages) / metrics.lead_count) * 100) : 0,
      tone: "amber" as Tone,
    },
    {
      label: "Sent",
      value: metrics?.sent_count ?? 0,
      pct: metrics?.lead_count ? formatPercent((metrics.sent_count ?? 0) / metrics.lead_count) : "0%",
      width: metrics?.lead_count ? Math.round((metrics.sent_count / metrics.lead_count) * 100) : 0,
      tone: "green" as Tone,
    },
    {
      label: "Replied",
      value: metrics?.response_count ?? 0,
      pct: metrics?.sent_count ? formatPercent((metrics.response_count ?? 0) / metrics.sent_count) : "0%",
      width: metrics?.sent_count ? Math.round((metrics.response_count / metrics.sent_count) * 100) : 0,
      tone: "green" as Tone,
    },
  ];
  return (
    <>
      <div className="discovery-status-strip">
        <StatusPill tone={statusTone(selectedRun?.status || "draft")}>Discovery</StatusPill>
        <strong>{selectedRun?.name || selectedRun?.id || "No discovery run selected"}</strong>
        <span>{selectedRun?.stage || "No stage"}</span>
        <span>{metrics?.pending_approval_count ?? 0} drafts waiting for approval</span>
      </div>

      <div className="stat-grid four">
        <StatCard label="Results found" value={String(metrics?.lead_count ?? 0)} />
        <StatCard label="Qualified" value={String(metrics?.qualified_lead_count ?? 0)} />
        <StatCard label="Awaiting approval" value={String(metrics?.pending_approval_count ?? 0)} muted />
        <StatCard label="Reply rate" value={formatPercent(metrics?.response_rate)} />
      </div>

      <Card title="Discovery funnel" meta={<StatusPill tone={statusTone(selectedRun?.status || "draft")}>{selectedRun?.status || "idle"}</StatusPill>}>
        <div className="funnel">
          {funnel.map((row) => (
            <div className="funnel-row" key={row.label}>
              <span>{row.label}</span>
              <div className="bar-track">
                <i className={`tone-${row.tone}`} style={{ width: `${Math.max(row.width, row.value ? 3 : 0)}%` }} />
              </div>
              <strong>{row.value}</strong>
              <em>{row.pct}</em>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}

function approvedCount(messages: Array<{ status: string }>) {
  return messages.filter((message) => ["approved", "sent", "replied"].includes(message.status)).length;
}
