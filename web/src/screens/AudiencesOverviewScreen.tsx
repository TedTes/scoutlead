import { ArrowRight, LoaderCircle, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAppData } from "../state/app-data";
import type { AudiencePerformance, DiscoveryResult } from "../types/domain";

export function AudiencesOverviewScreen({ onOpenAudience }: { onOpenAudience: (id: string) => void }) {
  const { productContacts, selectedProductId, territoryApi } = useAppData();
  const [rows, setRows] = useState<AudiencePerformance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const summary = useMemo(() => summarizeAudiences(rows, productContacts), [productContacts, rows]);

  useEffect(() => {
    let active = true;
    if (!selectedProductId) {
      setRows([]);
      setLoading(false);
      return () => { active = false; };
    }
    setLoading(true);
    setError("");
    void territoryApi.getAudiencePerformance(selectedProductId)
      .then((result) => { if (active) setRows(result); })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : String(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedProductId, territoryApi]);

  return (
    <section className="audiences-overview">
      <header className="audiences-overview-mobile-heading">
        <span>Account-wide performance</span>
        <h1>Overview</h1>
      </header>
      {loading ? <div className="audiences-overview-empty"><LoaderCircle className="sl-spin-icon" size={18} /> Loading audiences</div> : null}
      {!loading && error ? <div className="audiences-overview-empty error">{error}</div> : null}
      {!loading && !error && !rows.length ? <div className="audiences-overview-empty">No audiences yet.</div> : null}
      {!loading && !error && rows.length ? (
        <>
          <section className="audiences-overview-metrics" aria-label="Lead funnel">
            <OverviewMetric label="Leads" value={summary.leads} detail="Unique across all audiences" />
            <OverviewMetric label="Shortlisted" value={summary.shortlisted} detail={formatRate(summary.shortlistRate)} />
            <OverviewMetric label="Contacted" value={summary.contacted} detail={formatRate(summary.contactRate)} />
            <OverviewMetric label="Ready audiences" value={`${summary.ready} / ${rows.length}`} detail={summary.latestRun ? `Latest collection ${formatRecency(summary.latestRun)}` : "No collection yet"} />
          </section>

          <section className="audiences-overview-breakdown" aria-label="Audience readiness and coverage">
            <div className="audiences-overview-panel">
              <header><strong>Audience readiness</strong><span>Where collection stands</span></header>
              <div className="overview-status-list">
                <OverviewStatus label="Ready" value={summary.ready} tone="green" />
                <OverviewStatus label="Building or validating" value={summary.building} tone="amber" />
                <OverviewStatus label="Needs attention" value={summary.attention} tone="red" />
              </div>
            </div>
            <div className="audiences-overview-panel">
              <header><strong>Coverage by business type</strong><span>Current audience batches</span></header>
              <div className="overview-coverage-list">
                {summary.byNiche.slice(0, 5).map((item) => (
                  <div key={item.label}>
                    <span><strong>{item.label}</strong><small>{item.audiences} {item.audiences === 1 ? "audience" : "audiences"}</small></span>
                    <em>{item.leads} leads</em>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="audiences-overview-table-section">
            <header><strong>Audience performance</strong><span>Select an audience to inspect its leads.</span></header>
            <div className="audiences-overview-list">
              <div className="audiences-overview-columns" aria-hidden="true">
                <span>Audience</span><span>Leads</span><span>Shortlisted</span><span>Contacted</span><span>Status</span><span />
              </div>
              {rows.map((row) => (
                <button className="audiences-overview-row" key={row.audience_id} type="button" onClick={() => onOpenAudience(row.audience_id)}>
                  <span className="audiences-overview-name"><Users size={16} /><span><strong>{row.label}</strong><small>{row.place_label} · {row.radius_km} km</small></span></span>
                  <strong>{row.lead_count}</strong>
                  <span><strong>{row.shortlisted_count}</strong><small>{formatRate(row.shortlist_rate)}</small></span>
                  <span><strong>{row.contacted_count}</strong><small>{formatRate(row.contact_rate)}</small></span>
                  <span className={`audiences-overview-state state-${row.state}`}>{stateLabel(row.state)}</span>
                  <ArrowRight size={15} />
                </button>
              ))}
            </div>
          </section>
        </>
      ) : null}
    </section>
  );
}

function OverviewMetric({ detail, label, value }: { detail: string; label: string; value: number | string }) {
  return <article><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function OverviewStatus({ label, tone, value }: { label: string; tone: "green" | "amber" | "red"; value: number }) {
  return <div><span><i className={`overview-status-dot ${tone}`} />{label}</span><strong>{value}</strong></div>;
}

function summarizeAudiences(rows: AudiencePerformance[], contacts: DiscoveryResult[]) {
  const leads = contacts.length;
  const shortlisted = contacts.filter((contact) => Boolean(contact.shortlisted_at)).length;
  const contacted = contacts.filter((contact) => Boolean(contact.last_contacted_at || contact.latest_outcome)).length;
  const readyStates = new Set(["ready", "partial"]);
  const buildingStates = new Set(["setup", "queued", "scoring", "retrying", "waiting_validation"]);
  const byNiche = new Map<string, { audiences: number; label: string; leads: number }>();
  for (const row of rows) {
    const label = row.niche_label || "Other";
    const current = byNiche.get(label) || { audiences: 0, label, leads: 0 };
    current.audiences += 1;
    current.leads += row.lead_count;
    byNiche.set(label, current);
  }
  const latestTimestamps = rows
    .map((row) => row.latest_run_at ? new Date(row.latest_run_at).getTime() : Number.NaN)
    .filter(Number.isFinite);
  return {
    leads,
    shortlisted,
    contacted,
    shortlistRate: leads ? shortlisted / leads : 0,
    contactRate: leads ? contacted / leads : 0,
    ready: rows.filter((row) => readyStates.has(row.state)).length,
    building: rows.filter((row) => buildingStates.has(row.state)).length,
    attention: rows.filter((row) => !readyStates.has(row.state) && !buildingStates.has(row.state)).length,
    latestRun: latestTimestamps.length ? new Date(Math.max(...latestTimestamps)).toISOString() : "",
    byNiche: [...byNiche.values()].sort((a, b) => b.leads - a.leads || b.audiences - a.audiences),
  };
}

function formatRate(value: number) {
  return `${Math.round(value * 100)}% of leads`;
}

function formatRecency(value: string) {
  const elapsed = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(elapsed) || elapsed < 0) return "recently";
  const hours = Math.floor(elapsed / 3_600_000);
  if (hours < 1) return "less than an hour ago";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function stateLabel(value: string) {
  if (value === "waiting_validation") return "Validating";
  if (value === "ready" || value === "partial") return "Ready";
  if (value === "failed") return "Needs attention";
  return value.replace(/_/g, " ");
}
