import { Play, Plus } from "lucide-react";
import { useState } from "react";
import { useAppData } from "../state/app-data";
import { Card, ChipSet, PageHeader, StatusPill } from "../shared-ui";
import type { Lead } from "../types/domain";
import { scoreTone, statusTone } from "../utils/status";

export function LeadsScreen() {
  const { snapshot, addSeedLeads, runCampaign } = useAppData();
  const [seedJson, setSeedJson] = useState("");
  const [expandedLeadId, setExpandedLeadId] = useState("");
  const leads = snapshot.leads;
  const qualified = leads.filter((lead) => lead.qualification?.qualified).length;
  const review = leads.filter((lead) => lead.status === "discovered" || lead.status === "researched").length;
  const disqualified = leads.filter((lead) => lead.status === "disqualified").length;

  return (
    <>
      <PageHeader
        title="Lead discovery"
        subtitle="Matched companies with AI research and qualification. Click a row for the full dossier."
        actions={
          <>
            <button className="secondary">Export CSV</button>
            <button onClick={() => runCampaign()}>
              <Play size={14} />
              Run discovery
            </button>
          </>
        }
      />

      <div className="tabs">
        <button className="active">All - {leads.length}</button>
        <button>Qualified - {qualified}</button>
        <button>Review - {review}</button>
        <button>Disqualified - {disqualified}</button>
      </div>

      <div className="table-shell">
        {leads.length === 0 ? (
          <p className="empty-copy">No leads yet. Add seed leads or run the selected campaign.</p>
        ) : (
          <table className="data-table leads-table">
            <thead>
              <tr>
                <th></th>
                <th>Company</th>
                <th>Contact</th>
                <th>Location</th>
                <th>Signals</th>
                <th>Score</th>
                <th>Stage</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <LeadRows
                  lead={lead}
                  expanded={expandedLeadId === lead.id}
                  onToggle={() => setExpandedLeadId(expandedLeadId === lead.id ? "" : lead.id)}
                  key={lead.id}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Card title="Seed leads">
        <div className="seed-import">
          <textarea
            value={seedJson}
            rows={7}
            placeholder='Paste a JSON array of real seed leads.'
            onChange={(event) => setSeedJson(event.target.value)}
          />
          <button
            onClick={() => {
              if (!seedJson.trim()) return;
              const seeds = JSON.parse(seedJson);
              if (Array.isArray(seeds)) void addSeedLeads(seeds);
            }}
          >
            <Plus size={14} />
            Add seeds
          </button>
        </div>
      </Card>
    </>
  );
}

function LeadRows({ lead, expanded, onToggle }: { lead: Lead; expanded: boolean; onToggle: () => void }) {
  const score = lead.qualification?.score ?? lead.research?.confidence;
  const signals = [
    ...(lead.research?.signals || []),
    ...(lead.research?.pain_indicators || []).map((signal) => `pain: ${signal}`),
  ].slice(0, 4);

  return (
    <>
      <tr onClick={onToggle}>
        <td>
          <i className="row-marker" />
        </td>
        <td>
          <strong>{lead.company_name}</strong>
          <span>{lead.website_url || lead.research?.website_url || "No website"}</span>
        </td>
        <td>
          {lead.research?.contact_name || lead.contact_email || "-"}
          <span>{lead.research?.contact_email || lead.contact_email || ""}</span>
        </td>
        <td>{lead.geography || lead.research?.geography || "-"}</td>
        <td>{signals.length ? <ChipSet values={signals} small /> : <span>{lead.description || "-"}</span>}</td>
        <td>{score === undefined ? "-" : <StatusPill tone={scoreTone(score)}>{score}</StatusPill>}</td>
        <td>
          <StatusPill tone={statusTone(lead.status)}>{lead.status}</StatusPill>
        </td>
      </tr>
      {expanded && (
        <tr className="lead-dossier-row">
          <td colSpan={7}>
            <div className="lead-dossier">
              <section>
                <strong>Research</strong>
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
          </td>
        </tr>
      )}
    </>
  );
}
