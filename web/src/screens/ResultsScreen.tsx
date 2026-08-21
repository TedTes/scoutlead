import { useState } from "react";
import { ChipSet, StatusPill } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { DiscoveryResult } from "../types/domain";
import { isLiveResultStage, resultStageLabel, scoreTone, statusTone } from "../utils/status";

type ResultFilter = "all" | "qualified" | "review" | "disqualified";

export function ResultsScreen() {
  const { snapshot } = useAppData();
  const [expandedContactId, setExpandedContactId] = useState("");
  const [filter, setFilter] = useState<ResultFilter>("all");
  const contacts = snapshot.results;
  const qualified = contacts.filter((contact) => contact.qualification?.qualified).length;
  const review = contacts.filter((contact) => contact.status === "discovered" || contact.status === "researched").length;
  const disqualified = contacts.filter((contact) => contact.status === "disqualified").length;
  const visibleContacts = contacts.filter((contact) => {
    if (filter === "qualified") return Boolean(contact.qualification?.qualified);
    if (filter === "review") return contact.status === "discovered" || contact.status === "researched";
    if (filter === "disqualified") return contact.status === "disqualified";
    return true;
  });

  return (
    <>
      <div className="tabs">
        <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
          All · {contacts.length}
        </button>
        <button className={filter === "qualified" ? "active" : ""} onClick={() => setFilter("qualified")}>
          Qualified · {qualified}
        </button>
        <button className={filter === "review" ? "active" : ""} onClick={() => setFilter("review")}>
          Review · {review}
        </button>
        <button className={filter === "disqualified" ? "active" : ""} onClick={() => setFilter("disqualified")}>
          Disqualified · {disqualified}
        </button>
      </div>

      <div className="lead-list-shell">
        {visibleContacts.length === 0 ? (
          <p className="empty-copy">No matching results yet. Add a product, connect a discovery source, then run discovery.</p>
        ) : (
          <div className="lead-list">
            <div className="lead-list-head" aria-hidden="true">
              <span>Company</span>
              <span>Contact</span>
              <span>Signals</span>
              <span>Score</span>
              <span>Status</span>
            </div>
            {visibleContacts.map((contact) => (
              <ResultRow
                contact={contact}
                expanded={expandedContactId === contact.id}
                onToggle={() => setExpandedContactId(expandedContactId === contact.id ? "" : contact.id)}
                key={contact.id}
              />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function ResultRow({ contact, expanded, onToggle }: { contact: DiscoveryResult; expanded: boolean; onToggle: () => void }) {
  const score = contact.qualification?.score ?? contact.research?.confidence;
  const url = contact.website_url || contact.research?.website_url || "";
  const preResearch = contact.status === "discovered" || contact.status === "researching";
  const owner = contact.research?.contact_name || contact.contact_email || contact.research?.contact_email || "";
  const ownerDetail = preResearch
    ? "researching..."
    : contact.research?.contact_email && contact.research.contact_email !== owner
      ? contact.research.contact_email
      : "";
  const signals = [
    ...(contact.research?.signals || []),
    ...(contact.research?.pain_indicators || []).map((signal) => `pain: ${signal}`),
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
          <strong>{contact.company_name}</strong>
          <span>{contact.geography || contact.research?.geography || "-"}</span>
        </div>
        <div className="lead-contact-cell">
          <strong>{owner || "-"}</strong>
          <span className={preResearch ? "muted" : ""}>{ownerDetail || "-"}</span>
        </div>
        <div className="lead-signal-cell">
          {signals.length ? <ChipSet values={signals} small /> : <span>{contact.description || "No signal captured"}</span>}
        </div>
        <div className="lead-score-cell">
          {score === undefined ? <span className="muted">-</span> : <StatusPill tone={scoreTone(score)}>{score}</StatusPill>}
        </div>
        <div className="lead-stage-cell">
          <StatusPill tone={statusTone(contact.status)} dot={isLiveResultStage(contact.status)}>
            {resultStageLabel(contact.status)}
          </StatusPill>
        </div>
      </div>
      {expanded ? (
        <div className="lead-dossier">
          <section>
            <strong>Research</strong>
            {url ? <p className="dossier-website">{displayUrl(url)}</p> : null}
            <p>{contact.research?.summary || "No research captured yet."}</p>
          </section>
          <section>
            <strong>Qualification</strong>
            <p>{contact.qualification?.rationale || "No qualification result yet."}</p>
          </section>
          <section>
            <strong>Next step</strong>
            <p>{contact.qualification?.recommended_next_step || "Review manually."}</p>
          </section>
        </div>
      ) : null}
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
