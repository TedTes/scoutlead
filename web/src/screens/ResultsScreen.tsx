import { AlertTriangle, Copy, Download, Globe, Mail, MapPin, MoreVertical, Phone, Play, RotateCw, Search, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { OverviewScreen } from "./OverviewScreen";
import { useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { DiscoveryResult, SourceRequestSource } from "../types/domain";
import { mergeSourceProviders, normalizeActiveSourceIds } from "../utils/source-providers";

type ResultFilter = "all" | "reachable";
type ResultSort = "contact" | "score" | "name";

export function ResultsScreen() {
  const {
    activeSourceIds,
    runSourceRequest,
    selectedDiscoveryRun,
    selectedDiscoveryRunId,
    selectedProduct,
    selectedProductId,
    setSelectedDiscoveryRunId,
    deleteDiscoveryRuns,
    renameDiscoveryRun,
    snapshot,
    sourceProviders,
  } = useAppData();
  const { showToast } = useToast();
  const [selectedContactId, setSelectedContactId] = useState("");
  const [draftPrompt, setDraftPrompt] = useState("");
  const [filter, setFilter] = useState<ResultFilter>("all");
  const [sort, setSort] = useState<ResultSort>("contact");
  const [selectedSources, setSelectedSources] = useState<SourceRequestSource[]>([]);
  const [running, setRunning] = useState(false);
  const [runMenuOpen, setRunMenuOpen] = useState(false);
  const runMenuRef = useRef<HTMLDivElement | null>(null);

  const contacts = selectedDiscoveryRunId ? snapshot.results : [];
  const providers = useMemo(() => mergeSourceProviders(sourceProviders), [sourceProviders]);
  const connectedProviders = useMemo(() => providers.filter((provider) => provider.configured), [providers]);
  const runPrompt = getRunPrompt(selectedDiscoveryRun);
  const query = draftPrompt.trim() || runPrompt;
  const selectedSource = selectedSources[0] || "";
  const reachableContacts = contacts.filter((contact) => isReachableContact(contact)).length;
  const visibleContacts = contacts
    .filter((contact) => {
      if (filter === "reachable") return isReachableContact(contact);
      return true;
    })
    .sort((a, b) => {
      if (sort === "name") return a.company_name.localeCompare(b.company_name);
      if (sort === "score") return contactScore(b) - contactScore(a);
      return Number(isReachableContact(b)) - Number(isReachableContact(a)) || contactScore(b) - contactScore(a);
    });
  const exportName = selectedDiscoveryRun?.name || selectedProduct?.product_name || "contacts";
  const selectedContact = contacts.find((contact) => contact.id === selectedContactId);

  useEffect(() => {
    setDraftPrompt(runPrompt);
    setSelectedContactId("");
    setFilter("all");
  }, [selectedDiscoveryRunId, runPrompt]);

  useEffect(() => {
    setRunMenuOpen(false);
  }, [selectedDiscoveryRunId]);

  useEffect(() => {
    if (!runMenuOpen) return undefined;
    const closeMenu = (event: MouseEvent) => {
      if (!runMenuRef.current?.contains(event.target as Node)) {
        setRunMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", closeMenu);
    return () => document.removeEventListener("mousedown", closeMenu);
  }, [runMenuOpen]);

  useEffect(() => {
    setSelectedSources((current) => {
      const fromRun = getRunSource(selectedDiscoveryRun);
      const validCurrent = current.filter((sourceId) => connectedProviders.some((provider) => provider.id === sourceId));
      const validActive = normalizeActiveSourceIds(activeSourceIds, connectedProviders).slice(0, 1);
      if (validActive.length) return validActive;
      if (validCurrent.length) return validCurrent.slice(0, 1);
      if (fromRun && connectedProviders.some((provider) => provider.id === fromRun)) return [fromRun];
      return connectedProviders[0] ? [connectedProviders[0].id] : [];
    });
  }, [activeSourceIds, connectedProviders, selectedDiscoveryRun]);

  const updateSearch = async () => {
    const request = draftPrompt.trim();
    if (!selectedProductId || !request || !selectedSource || running) return;
    setRunning(true);
    try {
      const result = await runSourceRequest({
        product_id: selectedProductId,
        source: selectedSource,
        name: selectedDiscoveryRun?.name || undefined,
        prompt: request,
        max_results: selectedDiscoveryRun?.max_leads || 25,
        run_immediately: true,
      });
      if (result) {
        const foundCount = result.summary?.discovered_lead_count ?? 0;
        showToast({
          title: foundCount ? "Updated search complete" : "Search finished",
          message: foundCount ? `${foundCount} contact${foundCount === 1 ? "" : "s"} found.` : "No contacts were returned. Try another search.",
          tone: foundCount ? "green" : "amber",
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Search failed", message, tone: "red" });
    } finally {
      setRunning(false);
    }
  };

  const renameCurrentRun = async () => {
    if (!selectedDiscoveryRun) return;
    const nextName = window.prompt("Rename run", selectedDiscoveryRun.name || runTitle("", query));
    if (!nextName?.trim()) return;
    await renameDiscoveryRun(selectedDiscoveryRun.id, nextName.trim());
    setRunMenuOpen(false);
    showToast({ title: "Run renamed", tone: "green" });
  };

  const deleteCurrentRun = async () => {
    if (!selectedDiscoveryRun) return;
    const confirmed = window.confirm(`Delete ${runTitle(selectedDiscoveryRun.name || "", query)}? This removes the saved results for this run.`);
    if (!confirmed) return;
    await deleteDiscoveryRuns([selectedDiscoveryRun.id]);
    setSelectedDiscoveryRunId("");
    setRunMenuOpen(false);
    showToast({ title: "Run deleted", message: "The saved contact list was removed.", tone: "green" });
  };

  const rerunCurrentSearch = () => {
    setRunMenuOpen(false);
    void updateSearch();
  };

  if (!selectedDiscoveryRun) {
    return <OverviewScreen />;
  }

  if (!contacts.length) {
    return <OverviewScreen emptyMessage="No contacts were returned for this run. Try a different business type, location, or wording." />;
  }

  return (
    <section className="results-workspace">
      <SearchStrip
        draftPrompt={draftPrompt}
        onChange={setDraftPrompt}
        onSubmit={updateSearch}
        query={runPrompt}
        running={running}
        ready={Boolean(selectedProductId && draftPrompt.trim().length >= 4 && selectedSource)}
      />

      <header className="results-hero compact">
        <div className="results-actions">
          <div className="results-menu-control" ref={runMenuRef}>
            <button
              aria-expanded={runMenuOpen}
              aria-label="Run actions"
              className="menu-button"
              type="button"
              onClick={() => setRunMenuOpen((open) => !open)}
            >
              <MoreVertical size={18} />
            </button>
            {runMenuOpen ? (
              <div className="action-menu">
                <button
                  type="button"
                  disabled={!visibleContacts.length}
                  onClick={() => exportContactsCsv(visibleContacts.length ? visibleContacts : contacts, exportName)}
                >
                  <Download size={14} />
                  Export CSV
                </button>
                <button type="button" onClick={() => void renameCurrentRun()}>
                  Rename run
                </button>
                <button type="button" onClick={rerunCurrentSearch}>
                  <RotateCw size={14} />
                  Re-run search
                </button>
                <button className="danger-item" type="button" onClick={() => void deleteCurrentRun()}>
                  <Trash2 size={14} />
                  Delete this run
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <div className="results-filterbar">
        <div>
          <button className={filter === "all" ? "active" : ""} type="button" onClick={() => setFilter("all")}>
            All
            <span>{contacts.length}</span>
          </button>
          <button className={filter === "reachable" ? "active" : ""} type="button" onClick={() => setFilter("reachable")}>
            Reachable
            <span>{reachableContacts}</span>
          </button>
        </div>
        <div className="sort-tabs">
          <button className={sort === "contact" ? "active" : ""} type="button" onClick={() => setSort("contact")}>
            Contact
          </button>
          <button className={sort === "score" ? "active" : ""} type="button" onClick={() => setSort("score")}>
            Score
          </button>
          <button className={sort === "name" ? "active" : ""} type="button" onClick={() => setSort("name")}>
            Name
          </button>
        </div>
      </div>

      {visibleContacts.length ? (
        <ul className="contact-card-list">
          {visibleContacts.map((contact) => (
            <ContactCard
              contact={contact}
              key={contact.id}
              onOpen={() => setSelectedContactId(contact.id)}
            />
          ))}
        </ul>
      ) : (
        <section className="result-empty-card">
          <strong>No contacts match this view.</strong>
          <p>
            {contacts.length
              ? "Change the filter to inspect the contacts in this run."
              : "This run has no contacts yet."}
          </p>
        </section>
      )}

      <ContactDrawer contact={selectedContact} onClose={() => setSelectedContactId("")} />
    </section>
  );
}

function SearchStrip({
  draftPrompt,
  onChange,
  onSubmit,
  query,
  ready,
  running,
}: {
  draftPrompt: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  query: string;
  ready: boolean;
  running: boolean;
}) {
  return (
    <form
      className={running ? "searchbar is-running" : "searchbar"}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <Search size={15} />
      <input
        aria-label="Search prompt"
        placeholder={query || "Describe the businesses to find"}
        value={draftPrompt}
        onChange={(event) => onChange(event.target.value)}
      />
      <button
        aria-label={running ? "Finding contacts" : "Find contacts"}
        className="runbtn icon-run"
        disabled={!ready || running}
        title={running ? "Finding contacts" : "Find contacts"}
        type="submit"
      >
        <Play size={13} />
      </button>
    </form>
  );
}

function ContactCard({ contact, onOpen }: { contact: DiscoveryResult; onOpen: () => void }) {
  const score = contactScore(contact);

  return (
    <li>
      <article
        className={isReachableContact(contact) ? "contact-card" : "contact-card no-contact"}
        role="button"
        tabIndex={0}
        onClick={onOpen}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onOpen();
          }
        }}
      >
        <div className="contact-main">
          <span className={`score-ring ${scoreClass(score)}`}>
            <strong>{score}</strong>
          </span>
          <span className="contact-identity">
            <strong>{contact.company_name}</strong>
            <small>
              {contact.research?.business_type || contact.description || "Business"}
              {contact.geography || contact.research?.geography ? (
                <>
                  <MapPin size={12} />
                  {contact.geography || contact.research?.geography}
                </>
              ) : null}
            </small>
          </span>
        </div>
        <div className="contact-actions" aria-label="Contact availability">
          {contact.contact_email || contact.research?.contact_email ? (
            <span className="contact-icon has" title="Email found">
              <Mail size={15} />
            </span>
          ) : (
            <span className="contact-icon missing" title="No email found">
              <Mail size={15} />
            </span>
          )}
          {getPhone(contact) ? (
            <span className="contact-icon has" title="Phone found">
              <Phone size={15} />
            </span>
          ) : (
            <span className="contact-icon missing" title="No phone found">
              <Phone size={15} />
            </span>
          )}
          {!isReachableContact(contact) ? (
            <span className="no-contact-pill">
              <AlertTriangle size={13} />
              No contact
            </span>
          ) : null}
        </div>
      </article>
    </li>
  );
}

function ContactDrawer({ contact, onClose }: { contact: DiscoveryResult | undefined; onClose: () => void }) {
  const { showToast } = useToast();
  const open = Boolean(contact);
  const score = contact ? contactScore(contact) : 0;
  const signals = contact ? contactSignals(contact) : [];
  const website = contact?.website_url || contact?.research?.website_url || "";
  const email = contact?.contact_email || contact?.research?.contact_email || "";
  const phone = contact ? getPhone(contact) : "";
  const contactName = contact ? getContactName(contact) : "";
  const address = contact ? getAddress(contact) : "";
  const rating = contact ? getRating(contact) : "";
  const reviewCount = contact ? getReviewCount(contact) : "";
  const price = contact ? getPrice(contact) : "";
  const posted = contact ? getPostedDate(contact) : "";
  const confidence = contact?.research?.confidence ? `${contact.research.confidence}%` : "—";
  const evidenceNotes = contact
    ? [
        ...(contact.research?.pain_indicators || []),
        ...(contact.research?.disqualifiers || []),
        ...(contact.qualification?.criteria || []).flatMap((criterion) => criterion.evidence || []),
      ].filter(Boolean)
    : [];

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose, open]);

  const copy = async (value: string, label: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      showToast({ title: `${label} copied`, tone: "green" });
    } catch {
      showToast({ title: "Copy failed", message: `Could not copy ${label.toLowerCase()}.`, tone: "red" });
    }
  };

  return (
    <div className={`contact-drawer-overlay${open ? " open" : ""}`} aria-hidden={!open}>
      <button className="contact-drawer-backdrop" type="button" aria-label="Close details" onClick={onClose} />
      <aside className="contact-drawer-panel" aria-label="Contact details">
        {contact ? (
          <>
            <header className="contact-drawer-header">
              <div className="drawer-title-row">
                <span className={`score-ring large ${scoreClass(score)}`}>
                  <strong>{score}</strong>
                </span>
                <div>
                  <h2>{contact.company_name}</h2>
                  <p>
                    {contact.research?.business_type || contact.description || "Business"}
                    {contact.geography || contact.research?.geography ? ` · ${contact.geography || contact.research?.geography}` : ""}
                  </p>
                </div>
              </div>
              <button className="drawer-close" type="button" onClick={onClose} aria-label="Close">
                <X size={18} />
              </button>
            </header>

            <div className="drawer-body">
              <p className="drawer-summary">{contact.research?.summary || contact.description || "No research captured yet."}</p>

              <div className="drawer-chip-row">
                {signals.slice(0, 6).map((signal) => (
                  <span key={signal}>{signal}</span>
                ))}
              </div>

              <dl className="drawer-detail-list">
                <DrawerRow icon={<MapPin size={16} />} label="Address">
                  {address || contact.geography || contact.research?.geography || "No address found"}
                </DrawerRow>
                <DrawerRow icon={<Globe size={16} />} label="Website">
                  {website ? (
                    <a href={website} target="_blank" rel="noreferrer">
                      {displayUrl(website)}
                    </a>
                  ) : (
                    <span>No website found</span>
                  )}
                </DrawerRow>
                <DrawerRow icon={<Mail size={16} />} label="Contact">
                  {contactName || contact?.research?.contact_name || "No contact name found"}
                </DrawerRow>
                <DrawerRow icon={<Mail size={16} />} label="Email">
                  {email ? (
                    <button type="button" onClick={() => copy(email, "Email")}>
                      {email}
                      <Copy size={13} />
                    </button>
                  ) : (
                    <span>No email found</span>
                  )}
                </DrawerRow>
                <DrawerRow icon={<Phone size={16} />} label="Phone">
                  {phone || "No phone found"}
                </DrawerRow>
              </dl>

              <div className="drawer-mini-grid">
                <Mini label="Rating" value={rating || "—"} />
                <Mini label="Reviews" value={reviewCount || "—"} />
                <Mini label="Price" value={price || "—"} />
                <Mini label="Posted" value={posted || "—"} />
                <Mini label="Confidence" value={confidence} />
              </div>

              <section className="drawer-section">
                <h3>{contact.status === "disqualified" ? "Disqualification reason" : "Qualification"}</h3>
                <p>{disqualificationReason(contact) || contact.qualification?.rationale || "No qualification summary yet."}</p>
              </section>

              {evidenceNotes.length ? (
                <section className="drawer-section">
                  <h3>Evidence notes</h3>
                  <ul className="drawer-notes">
                    {evidenceNotes.slice(0, 5).map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                </section>
              ) : null}

            </div>

            <footer className="drawer-footer">
              <button className="secondary" type="button" onClick={onClose}>
                Close
              </button>
            </footer>
          </>
        ) : null}
      </aside>
    </div>
  );
}

function DrawerRow({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="drawer-row">
      <dt>
        <span>{icon}</span>
        {label}
      </dt>
      <dd>{children}</dd>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="drawer-mini">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function getRunPrompt(run: { source_input?: string | null; source_inputs?: Record<string, unknown> } | undefined) {
  const prompt = run?.source_inputs?.source_request_prompt;
  if (typeof prompt === "string" && prompt.trim()) return prompt.trim();
  const compiledQuery = run?.source_inputs?.compiled_query;
  if (typeof compiledQuery === "string" && compiledQuery.trim() && !compiledQuery.startsWith("http")) {
    return compiledQuery.trim();
  }
  if (run?.source_input?.trim() && !run.source_input.trim().startsWith("http")) return run.source_input.trim();
  return "";
}

function getRunSource(run: { source_inputs?: Record<string, unknown> } | undefined) {
  const source = run?.source_inputs?.source_request_source;
  return typeof source === "string" && source.trim() ? source.trim() : "";
}

function isReachableContact(contact: DiscoveryResult) {
  return Boolean(contact.contact_email || contact.research?.contact_email || getPhone(contact));
}

function contactStatusLabel(contact: DiscoveryResult) {
  if (contact.qualification?.qualified) return "Qualified";
  if (contact.status === "disqualified") return "Disqualified";
  return "Review";
}

function contactScore(contact: DiscoveryResult) {
  return Math.max(0, Math.min(100, Math.round(contact.qualification?.score ?? contact.research?.confidence ?? 0)));
}

function scoreClass(score: number) {
  if (score >= 90) return "score-great";
  if (score >= 80) return "score-good";
  if (score >= 70) return "score-warn";
  return "score-low";
}

function contactSignals(contact: DiscoveryResult) {
  const signals = [
    ...(contact.research?.signals || []),
    ...(contact.research?.pain_indicators || []).map((signal) => `Pain: ${signal}`),
    ...(contact.qualification?.criteria || []).flatMap((criterion) => criterion.evidence || []),
  ];
  return signals.length ? [...new Set(signals)].slice(0, 5) : [contact.status.replace(/_/g, " ")];
}

function disqualificationReason(contact: DiscoveryResult) {
  if (contact.status !== "disqualified") return "";
  const flags = contact.research?.disqualifiers?.length ? `Flags: ${contact.research.disqualifiers.join(", ")}` : "";
  return [contact.qualification?.rationale, flags].filter(Boolean).join(" ");
}

function runTitle(runName: string, query: string) {
  const cleaned = runName.replace(/\s+discovery\s+\d{4}-.*/i, "").trim();
  if (cleaned && !/^contacts$/i.test(cleaned) && !/\bdiscovery\b/i.test(runName)) return titleCase(cleaned);
  const intentTitle = titleFromQuery(query);
  if (intentTitle) return intentTitle;
  const beforeWith = query.split(/\s+with\s+/i)[0]?.trim();
  return titleCase(beforeWith || "Contact list");
}

function titleFromQuery(query: string) {
  const clean = query
    .replace(/^(list|find|get|show)\s+/i, "")
    .replace(/^(independent|local|small)\s+/i, "")
    .trim();
  const match = clean.match(/^(.+?)\s+(?:in|near|around)\s+(.+?)(?:\s+(?:with|that|who|which|where)\b|$)/i);
  if (!match) return "";
  const subject = match[1]
    .replace(/\bcontacts?\b/gi, "")
    .replace(/\bcompanies\b/gi, "businesses")
    .trim();
  const location = match[2].replace(/[,.].*$/, "").trim();
  if (!subject || !location) return "";
  return `${titleCase(subject)} · ${titleCase(location)}`;
}

function titleCase(value: string) {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => `${word.slice(0, 1).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

function displayUrl(value: string) {
  if (!value) return "";
  try {
    const parsed = new URL(value);
    return parsed.hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

function getAddress(contact: DiscoveryResult) {
  return getRawString(contact, [
    "formattedAddress",
    "formatted_address",
    "address",
    "streetAddress",
    "fullAddress",
    "location.address",
    "location.name",
    "data.location",
  ]);
}

function getRating(contact: DiscoveryResult) {
  const value = getRawNumber(contact, ["rating", "averageRating", "stars", "reviewRating", "stats.rating"]);
  return value ? value.toFixed(1) : "";
}

function getReviewCount(contact: DiscoveryResult) {
  const value = getRawNumber(contact, [
    "userRatingCount",
    "user_ratings_total",
    "reviewCount",
    "reviewsCount",
    "reviews",
    "stats.reviews",
  ]);
  return value ? String(value) : "";
}

function getPhone(contact: DiscoveryResult) {
  return getRawString(contact, [
    "normalized_contact_phone",
    "contact_phone",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "phone",
    "phoneNumber",
    "phone_number",
    "telephone",
    "contactPhone",
    "sellerPhone",
    "ownerPhone",
    "seller.phone",
    "contact.phone",
    "data.phone",
  ]);
}

function getContactName(contact: DiscoveryResult) {
  return getRawString(contact, [
    "normalized_contact_name",
    "contact_name",
    "contactName",
    "sellerName",
    "ownerName",
    "seller.name",
    "contact.name",
    "data.sellerName",
  ]);
}

function getPrice(contact: DiscoveryResult) {
  return getRawString(contact, ["price", "priceText", "price.text", "amount", "listing.price", "data.price"]);
}

function getPostedDate(contact: DiscoveryResult) {
  return getRawString(contact, [
    "postedAt",
    "posted_at",
    "datePosted",
    "publishedAt",
    "createdAt",
    "listing.postedAt",
    "data.postedAt",
  ]);
}

function getRawString(contact: DiscoveryResult, keys: string[]) {
  for (const raw of getRawObjects(contact)) {
    for (const key of keys) {
      const text = rawValueToString(getRawValue(raw, key));
      if (text) return text;
    }
  }
  return "";
}

function getRawNumber(contact: DiscoveryResult, keys: string[]) {
  for (const raw of getRawObjects(contact)) {
    for (const key of keys) {
      const value = getRawValue(raw, key);
      if (typeof value === "number" && Number.isFinite(value)) return value;
      if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
    }
  }
  return 0;
}

function getRawObjects(contact: DiscoveryResult) {
  const values: Record<string, unknown>[] = [];
  for (const source of contact.raw_sources || []) {
    values.push(source);
    if (isRecord(source.raw)) {
      values.push(source.raw);
      if (isRecord(source.raw.raw)) values.push(source.raw.raw);
    }
  }
  return values;
}

function getRawValue(raw: Record<string, unknown>, key: string): unknown {
  if (key in raw) return raw[key];
  return key.split(".").reduce<unknown>((value, part) => {
    if (Array.isArray(value)) {
      const index = Number(part);
      return Number.isInteger(index) ? value[index] : undefined;
    }
    if (!isRecord(value)) return undefined;
    return value[part];
  }, raw);
}

function rawValueToString(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (isRecord(value)) {
    return rawValueToString(
      value.text ?? value.name ?? value.value ?? value.formatted ?? value.display ?? value.label,
    );
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const text = rawValueToString(item);
      if (text) return text;
    }
  }
  return "";
}

function exportContactsCsv(contacts: DiscoveryResult[], runName: string) {
  const rows = contacts.map((contact) => ({
    company: contact.company_name,
    email: contact.contact_email || contact.research?.contact_email || "",
    contact_name: getContactName(contact) || contact.research?.contact_name || "",
    phone: getPhone(contact),
    price: getPrice(contact),
    posted: getPostedDate(contact),
    website: contact.website_url || contact.research?.website_url || "",
    geography: contact.geography || contact.research?.geography || "",
    score: String(contactScore(contact)),
    status: contactStatusLabel(contact),
    signals: contactSignals(contact).join("; "),
    rationale: contact.qualification?.rationale || "",
  }));
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
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "contacts";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
