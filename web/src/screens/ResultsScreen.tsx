import { Download } from "lucide-react";
import { useState } from "react";
import { ChipSet, StatusPill } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { DiscoveryResult } from "../types/domain";
import { isLiveResultStage, resultStageLabel, scoreTone, statusTone } from "../utils/status";

type ResultFilter = "qualified" | "review" | "disqualified";

export function ResultsScreen() {
  const { selectedDiscoveryRun, selectedDiscoveryRunId, selectedProduct, snapshot } = useAppData();
  const [expandedContactId, setExpandedContactId] = useState("");
  const [filter, setFilter] = useState<ResultFilter>("qualified");
  const contacts = selectedDiscoveryRunId ? snapshot.results : [];
  const qualified = contacts.filter((contact) => contact.qualification?.qualified).length;
  const review = contacts.filter((contact) => isReviewContact(contact)).length;
  const disqualified = contacts.filter((contact) => contact.status === "disqualified").length;
  const visibleContacts = contacts.filter((contact) => {
    if (filter === "qualified") return Boolean(contact.qualification?.qualified);
    if (filter === "disqualified") return contact.status === "disqualified";
    return isReviewContact(contact);
  });
  const exportName = selectedDiscoveryRun?.name || selectedProduct?.product_name || "contacts";

  return (
    <>
      <section className="contacts-header">
        <div>
          <h1>Contacts</h1>
          <p>
            {selectedDiscoveryRun
              ? selectedDiscoveryRun.name
              : "Run a source request to create a saved contact list."}
          </p>
        </div>
      </section>

      <div className="results-toolbar">
        <div className="tabs">
          <button className={filter === "qualified" ? "active" : ""} onClick={() => setFilter("qualified")}>
            Qualified · {qualified}
          </button>
          <button className={filter === "review" ? "active" : ""} onClick={() => setFilter("review")}>
            Review · {review}
          </button>
          {disqualified ? (
            <button className={filter === "disqualified" ? "active" : ""} onClick={() => setFilter("disqualified")}>
              Filtered out · {disqualified}
            </button>
          ) : null}
        </div>
        <button
          className="secondary"
          type="button"
          disabled={!visibleContacts.length}
          onClick={() => exportContactsCsv(visibleContacts, exportName)}
        >
          <Download size={14} />
          Export CSV
        </button>
      </div>

      <div className="lead-list-shell">
        {visibleContacts.length === 0 ? (
          <div className="lead-list-empty">
            <p className="empty-copy">{emptyStateCopy(filter, contacts.length, disqualified)}</p>
            {filter !== "disqualified" && disqualified && contacts.length === disqualified ? (
              <button className="secondary" type="button" onClick={() => setFilter("disqualified")}>
                View filtered out contacts
              </button>
            ) : null}
          </div>
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

function emptyStateCopy(filter: ResultFilter, totalContacts: number, disqualifiedCount: number) {
  if (totalContacts === 0) {
    return "No contacts in this list yet. Use Find to create or rerun a source request.";
  }
  if (filter === "qualified") {
    return disqualifiedCount === totalContacts
      ? `All ${totalContacts} contact${totalContacts === 1 ? "" : "s"} found so far were filtered out.`
      : "No qualified contacts yet. Check Review for contacts still being evaluated.";
  }
  if (filter === "review") {
    return "Nothing waiting for review right now.";
  }
  return "No contacts have been filtered out.";
}

function isReviewContact(contact: DiscoveryResult) {
  if (contact.status === "disqualified" || contact.qualification?.qualified) return false;
  return ["discovered", "researching", "researched"].includes(contact.status);
}

function ResultRow({ contact, expanded, onToggle }: { contact: DiscoveryResult; expanded: boolean; onToggle: () => void }) {
  const score = contact.qualification?.score ?? contact.research?.confidence;
  const url = contact.website_url || contact.research?.website_url || "";
  const preResearch = contact.status === "discovered" || contact.status === "researching";
  const phone = getPhone(contact);
  const owner = contact.research?.contact_name || contact.contact_email || contact.research?.contact_email || phone || "";
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
            <strong>{contact.status === "disqualified" ? "Why it was filtered out" : "Why it matched"}</strong>
            <p>{disqualificationReason(contact) || contact.qualification?.rationale || "No qualification result yet."}</p>
          </section>
          <section>
            <strong>Source evidence</strong>
            <p>{sourceEvidence(contact) || contact.qualification?.recommended_next_step || "Review manually."}</p>
          </section>
        </div>
      ) : null}
    </article>
  );
}

function disqualificationReason(contact: DiscoveryResult) {
  if (contact.status !== "disqualified") return "";
  const flags = contact.research?.disqualifiers?.length ? `Flags: ${contact.research.disqualifiers.join(", ")}` : "";
  return [contact.qualification?.rationale, flags].filter(Boolean).join(" ");
}

function displayUrl(value: string) {
  try {
    const parsed = new URL(value);
    return parsed.hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

function getPhone(contact: DiscoveryResult) {
  for (const source of contact.raw_sources || []) {
    const raw = source.raw;
    if (isRecord(raw)) {
      const directPhone = raw.nationalPhoneNumber || raw.internationalPhoneNumber || raw.phone;
      if (typeof directPhone === "string" && directPhone.trim()) return directPhone;
      const nestedRaw = raw.raw;
      if (isRecord(nestedRaw)) {
        const nestedPhone = nestedRaw.nationalPhoneNumber || nestedRaw.internationalPhoneNumber || nestedRaw.phone;
        if (typeof nestedPhone === "string" && nestedPhone.trim()) return nestedPhone;
      }
    }
  }
  return "";
}

function sourceEvidence(contact: DiscoveryResult) {
  const source = contact.raw_sources?.[0];
  if (!source) return "";
  const parts = [
    typeof source.source === "string" ? source.source : contact.source,
    typeof source.query === "string" ? `query: ${source.query}` : "",
    getPhone(contact) ? `phone: ${getPhone(contact)}` : "",
  ].filter(Boolean);
  return parts.join(" | ");
}

function exportContactsCsv(contacts: DiscoveryResult[], runName: string) {
  const rows = contacts.map((contact) => {
    const signals = [
      ...(contact.research?.signals || []),
      ...(contact.research?.pain_indicators || []).map((signal) => `pain: ${signal}`),
    ];
    return {
      company: contact.company_name,
      contact: contact.research?.contact_name || "",
      email: contact.contact_email || contact.research?.contact_email || "",
      phone: getPhone(contact),
      website: contact.website_url || contact.research?.website_url || "",
      geography: contact.geography || contact.research?.geography || "",
      score: String(contact.qualification?.score ?? contact.research?.confidence ?? ""),
      status: resultStageLabel(contact.status),
      signals: signals.join("; "),
      rationale: contact.qualification?.rationale || "",
    };
  });
  const headers = Object.keys(rows[0] || { company: "" });
  const csv = [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => csvCell(row[header as keyof typeof row])).join(",")),
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${slugify(runName)}-contacts.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value: string | number | undefined) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}

function slugify(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "scoutlead";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
