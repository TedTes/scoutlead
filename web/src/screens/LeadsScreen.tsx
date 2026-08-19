import { useState } from "react";
import { useAppData } from "../state/app-data";
import { ChipSet, StatusPill } from "../shared-ui";
import type { Lead } from "../types/domain";
import { isLiveLeadStage, leadStageLabel, scoreTone, statusTone } from "../utils/status";

type LeadFilter = "all" | "qualified" | "review" | "disqualified";

export function LeadsScreen() {
  const { snapshot } = useAppData();
  const [expandedLeadId, setExpandedLeadId] = useState("");
  const [filter, setFilter] = useState<LeadFilter>("all");
  const leads = snapshot.leads;
  const qualified = leads.filter((lead) => lead.qualification?.qualified).length;
  const review = leads.filter((lead) => lead.status === "discovered" || lead.status === "researched").length;
  const disqualified = leads.filter((lead) => lead.status === "disqualified").length;
  const visibleLeads = leads.filter((lead) => {
    if (filter === "qualified") return Boolean(lead.qualification?.qualified);
    if (filter === "review") return lead.status === "discovered" || lead.status === "researched";
    if (filter === "disqualified") return lead.status === "disqualified";
    return true;
  });

  return (
    <>
      <div className="tabs">
        <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>All · {leads.length}</button>
        <button className={filter === "qualified" ? "active" : ""} onClick={() => setFilter("qualified")}>Qualified · {qualified}</button>
        <button className={filter === "review" ? "active" : ""} onClick={() => setFilter("review")}>Review · {review}</button>
        <button className={filter === "disqualified" ? "active" : ""} onClick={() => setFilter("disqualified")}>Disqualified · {disqualified}</button>
      </div>

      <div className="lead-list-shell">
        {visibleLeads.length === 0 ? (
          <p className="empty-copy">No matching leads yet. Run the selected campaign or change the filter.</p>
        ) : (
          <div className="lead-list">
            <div className="lead-list-head" aria-hidden="true">
              <span>Company</span>
              <span>Owner</span>
              <span>Signals</span>
              <span>Score</span>
              <span>Stage</span>
            </div>
            {visibleLeads.map((lead) => (
              <LeadRow
                lead={lead}
                expanded={expandedLeadId === lead.id}
                onToggle={() => setExpandedLeadId(expandedLeadId === lead.id ? "" : lead.id)}
                key={lead.id}
              />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function LeadRow({ lead, expanded, onToggle }: { lead: Lead; expanded: boolean; onToggle: () => void }) {
  const score = lead.qualification?.score ?? lead.research?.confidence;
  const url = lead.website_url || lead.research?.website_url || "";
  const preResearch = lead.status === "discovered" || lead.status === "researching";
  const owner = lead.research?.contact_name || lead.contact_email || lead.research?.contact_email || "";
  const ownerDetail = preResearch
    ? "researching..."
    : lead.research?.contact_email && lead.research.contact_email !== owner
      ? lead.research.contact_email
      : "";
  const signals = [
    ...(lead.research?.signals || []),
    ...(lead.research?.pain_indicators || []).map((signal) => `pain: ${signal}`),
  ].slice(0, 3);

  return (
    <article
      className={`lead-row-card${expanded ? " expanded" : ""}`}
      onClick={onToggle}
      role="button"
      aria-expanded={expanded}
    >
      <div className="lead-row-main">
        <div className="lead-company-cell">
          <strong>{lead.company_name}</strong>
          <span>{lead.geography || lead.research?.geography || "—"}</span>
        </div>
        <div className="lead-contact-cell">
          <strong>{owner || "—"}</strong>
          <span className={preResearch ? "muted" : ""}>{ownerDetail || "—"}</span>
        </div>
        <div className="lead-signal-cell">
          {signals.length ? <ChipSet values={signals} small /> : <span>{lead.description || "No signal captured"}</span>}
        </div>
        <div className="lead-score-cell">
          {score === undefined ? <span className="muted">–</span> : <StatusPill tone={scoreTone(score)}>{score}</StatusPill>}
        </div>
        <div className="lead-stage-cell">
          <StatusPill tone={statusTone(lead.status)} dot={isLiveLeadStage(lead.status)}>
            {leadStageLabel(lead.status)}
          </StatusPill>
        </div>
      </div>
      {expanded && (
        <div className="lead-dossier">
          <section>
            <strong>Research</strong>
            {url && <p className="dossier-website">{displayUrl(url)}</p>}
            <p>{lead.research?.summary || "No research captured yet."}</p>
          </section>
          <section>
            <strong>Qualification</strong>
            <p>{lead.qualification?.rationale || "No qualification result yet."}</p>
          </section>
          <section>
            <strong>Next step</strong>
            <p>{lead.qualification?.recommended_next_step || "Run qualification or review manually."}</p>
          </section>
        </div>
      )}
    </article>
  );
}

function displayUrl(value: string) {
  try {
    const parsed = new URL(value);
    return parsed.hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}
