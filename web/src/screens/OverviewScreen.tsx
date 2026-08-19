import { useAppData } from "../state/app-data";
import { Card, StatCard, StatusPill } from "../shared-ui";
import type { Conversation, Lead } from "../types/domain";
import type { Tone } from "../types/navigation";
import { formatPercent } from "../utils/format";
import { statusTone } from "../utils/status";

export function OverviewScreen() {
  const { selectedCampaign, snapshot } = useAppData();
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
  const recentResponses = recentConversationResponses(snapshot.conversations, snapshot.leads);

  return (
    <>
      <div className="campaign-status-strip">
        <StatusPill tone={statusTone(selectedCampaign?.status || "draft")}>Active campaign</StatusPill>
        <strong>{selectedCampaign?.name || selectedCampaign?.id || "No campaign selected"}</strong>
        <span>{selectedCampaign?.stage || "No stage"}</span>
        <span>{metrics?.pending_approval_count ?? 0} drafts waiting for approval</span>
      </div>

      <div className="stat-grid four">
        <StatCard label="Leads sourced" value={String(metrics?.lead_count ?? 0)} />
        <StatCard label="Qualified" value={String(metrics?.qualified_lead_count ?? 0)} />
        <StatCard label="Awaiting approval" value={String(metrics?.pending_approval_count ?? 0)} muted />
        <StatCard label="Reply rate" value={formatPercent(metrics?.response_rate)} />
      </div>

      <div className="split">
        <Card title="Conversion funnel" meta={<StatusPill tone={statusTone(selectedCampaign?.status || "draft")}>{selectedCampaign?.status || "idle"}</StatusPill>}>
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

        <Card title="Recent responses" meta={<button className="link-button">View all</button>}>
          {recentResponses.length === 0 ? (
            <p className="empty-copy">No responses recorded yet.</p>
          ) : (
            <div className="response-list">
              {recentResponses.map(({ company, label, time, tone }) => (
                <div className="response-row" key={`${company}-${time}`}>
                  <strong>
                    {company}
                    <span>Inbound reply</span>
                  </strong>
                  <StatusPill tone={tone}>{label}</StatusPill>
                  <time>{time}</time>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

function approvedCount(messages: Array<{ status: string }>) {
  return messages.filter((message) => ["approved", "sent", "replied"].includes(message.status)).length;
}

function recentConversationResponses(conversations: Conversation[], leads: Lead[]) {
  return conversations
    .flatMap((conversation) =>
      conversation.events
        .filter((event) => event.direction === "inbound")
        .map((event) => ({
          company: leads.find((lead) => lead.id === conversation.lead_id)?.company_name || "Unknown lead",
          label: event.classification?.intent || "unknown",
          time: new Date(event.created_at).toLocaleDateString(),
          tone: statusTone(event.classification?.intent || "unknown"),
        })),
    )
    .slice(0, 5);
}
