import { ArrowRight, LoaderCircle, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { useAppData } from "../state/app-data";
import type { AudiencePerformance } from "../types/domain";

export function AudiencesOverviewScreen({ onOpenAudience }: { onOpenAudience: (id: string) => void }) {
  const { selectedProductId, territoryApi } = useAppData();
  const [rows, setRows] = useState<AudiencePerformance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
      <header>
        <div>
          <span className="audiences-overview-kicker">Audience performance</span>
          <h1>Audiences</h1>
          <p>See which searches produce leads worth shortlisting and contacting.</p>
        </div>
      </header>
      {loading ? <div className="audiences-overview-empty"><LoaderCircle className="sl-spin-icon" size={18} /> Loading audiences</div> : null}
      {!loading && error ? <div className="audiences-overview-empty error">{error}</div> : null}
      {!loading && !error && !rows.length ? <div className="audiences-overview-empty">No audiences yet.</div> : null}
      {!loading && !error && rows.length ? (
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
      ) : null}
    </section>
  );
}

function formatRate(value: number) {
  return `${Math.round(value * 100)}% of leads`;
}

function stateLabel(value: string) {
  if (value === "waiting_validation") return "Validating";
  if (value === "ready" || value === "partial") return "Ready";
  if (value === "failed") return "Needs attention";
  return value.replace(/_/g, " ");
}
