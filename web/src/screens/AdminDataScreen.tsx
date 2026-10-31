import {
  Activity,
  Archive,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  ExternalLink,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { ApiClient } from "../api/client";
import type {
  AdminBusinessDetail,
  AdminBusinessSummary,
  AdminFactLineage,
  AdminFactLineageClaim,
  AdminFactLineageObservation,
  AdminOverview,
} from "../types/domain";

const emptyOverview: AdminOverview = {
  total: 0,
  active: 0,
  quarantined: 0,
  archived: 0,
  fully_validated: 0,
  needs_attention: 0,
  incomplete: 0,
  searchable: 0,
  trade_groups: [],
};

export function AdminDataScreen({ api }: { api: ApiClient }) {
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [overview, setOverview] = useState(emptyOverview);
  const [rows, setRows] = useState<AdminBusinessSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [quality, setQuality] = useState("");
  const [sort, setSort] = useState("score_asc");
  const [status, setStatus] = useState("");
  const [nicheSlug, setNicheSlug] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<AdminBusinessDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState<"add" | "edit" | "delete" | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      await api.getAdminAccess();
      setAllowed(true);
      const summary = await api.getAdminOverview();
      const tradeGroups = summary.trade_groups || [];
      const selectedNiche = tradeGroups.some((group) => group.slug === nicheSlug)
        ? nicheSlug
        : tradeGroups[0]?.slug || "";
      if (selectedNiche !== nicheSlug) setNicheSlug(selectedNiche);
      const businessPage = await api.getAdminBusinesses({
        q: search,
        quality,
        sort,
        status,
        niche_slug: selectedNiche,
        page,
        page_size: 50,
      });
      setOverview(summary);
      setRows(businessPage.items);
      setTotal(businessPage.total);
      setSelectedId((current) => (
        businessPage.items.some((row) => row.id === current)
          ? current
          : businessPage.items[0]?.id || ""
      ));
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      if (/administrator access required|403/i.test(message)) setAllowed(false);
      else setError(message);
    } finally {
      setLoading(false);
    }
  }, [api, nicheSlug, page, quality, search, sort, status]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 180);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (!selectedId || !allowed) {
      setDetail(null);
      return;
    }
    void api.getAdminBusiness(selectedId).then(setDetail).catch((cause) => {
      setError(cause instanceof Error ? cause.message : String(cause));
    });
  }, [allowed, api, selectedId]);

  const refreshDetail = async (result?: AdminBusinessDetail) => {
    if (result) {
      setDetail(result);
      setSelectedId(result.id);
    }
    await load();
  };

  if (allowed === false) {
    return (
      <section className="admin-denied">
        <ShieldAlert size={28} />
        <h1>Administrator access required</h1>
        <p>This data stewardship area is not available to your account.</p>
      </section>
    );
  }

  const pageHeader = typeof document !== "undefined"
    ? document.getElementById("admin-page-header")
    : null;

  return (
    <section className="admin-data-screen admin-business-data-screen">
      {pageHeader ? createPortal(<div className="admin-business-header">
        <div className="admin-metrics admin-business-metrics" aria-label="Business quality overview">
          <Metric label="Businesses" value={overview.total} />
          <Metric label="Validated" value={overview.fully_validated} tone="good" />
          <Metric label="Needs attention" value={overview.needs_attention} tone="warn" />
          <Metric label="Incomplete" value={overview.incomplete} />
          <Metric label="Searchable" value={overview.searchable} />
        </div>
        <button className="admin-primary-button" type="button" onClick={() => setDialog("add")}>
          <Plus size={15} /> Add business
        </button>
      </div>, pageHeader) : null}

      {overview.trade_groups.length ? (
        <nav className="admin-trade-chips" aria-label="Business trades">
          {overview.trade_groups.map((group) => (
            <button
              aria-pressed={group.slug === nicheSlug}
              className={group.slug === nicheSlug ? "active" : ""}
              key={group.slug}
              type="button"
              onClick={() => {
                setNicheSlug(group.slug);
                setPage(1);
                setSelectedId("");
              }}
            >
              <span>{group.label}</span>
              <strong>{group.count.toLocaleString()}</strong>
            </button>
          ))}
        </nav>
      ) : null}

      <div className="admin-toolbar">
        <label className="admin-search">
          <Search size={15} />
          <input
            aria-label="Search businesses"
            placeholder="Search name, address, domain, or phone"
            value={search}
            onChange={(event) => { setSearch(event.target.value); setPage(1); }}
          />
        </label>
        <select aria-label="Data quality" value={quality} onChange={(event) => { setQuality(event.target.value); setPage(1); }}>
          <option value="">All quality</option>
          <option value="poor">Poor · 0–64</option>
          <option value="review">Review · 65–84</option>
          <option value="reliable">Reliable · 85–100</option>
        </select>
        <select aria-label="Business state" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
          <option value="">All states</option>
          <option value="active">Active</option>
          <option value="quarantined">Quarantined</option>
          <option value="archived">Archived</option>
        </select>
        <select aria-label="Sort businesses" value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}>
          <option value="score_asc">Lowest quality first</option>
          <option value="score_desc">Highest quality first</option>
          <option value="name">Name A–Z</option>
        </select>
        <button className="admin-icon-button" title="Refresh" type="button" onClick={() => void load()}>
          <RefreshCw size={15} />
        </button>
      </div>

      {error ? <div className="admin-error"><CircleAlert size={15} /> {error}</div> : null}

      <div className="admin-workspace admin-leads-workspace">
        <div className="admin-table-pane">
          <table className="admin-business-table">
            <thead><tr><th>Business</th><th>Market</th><th>Data quality</th><th>State</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr className={row.id === selectedId ? "is-selected" : ""} key={row.id} onClick={() => setSelectedId(row.id)}>
                  <td><strong>{row.display_name}</strong><span>{row.niche_label || "Unclassified"}</span></td>
                  <td><strong>{row.market_key || "Unknown"}</strong><span>{row.address || row.geography || "No address"}</span></td>
                  <td><QualityScore row={row} /></td>
                  <td><StatusPill value={row.status} /></td>
                </tr>
              ))}
              {!loading && !rows.length ? <tr><td colSpan={4} className="admin-empty">No businesses match these filters.</td></tr> : null}
            </tbody>
          </table>
          <footer className="admin-pagination">
            <span>{total ? `${(page - 1) * 50 + 1}-${Math.min(page * 50, total)} of ${total}` : "0 results"}</span>
            <div>
              <button disabled={page === 1} title="Previous page" type="button" onClick={() => setPage((value) => Math.max(1, value - 1))}><ChevronLeft size={15} /></button>
              <button disabled={page * 50 >= total} title="Next page" type="button" onClick={() => setPage((value) => value + 1)}><ChevronRight size={15} /></button>
            </div>
          </footer>
        </div>

        <BusinessInspector
          api={api}
          detail={detail}
          onEdit={() => setDialog("edit")}
          onDelete={() => setDialog("delete")}
          onRefresh={refreshDetail}
        />
      </div>

      {dialog === "add" ? <BusinessForm api={api} mode="add" onClose={() => setDialog(null)} onSaved={(value) => { setDialog(null); void refreshDetail(value); }} /> : null}
      {dialog === "edit" && detail ? <BusinessForm api={api} mode="edit" detail={detail} onClose={() => setDialog(null)} onSaved={(value) => { setDialog(null); void refreshDetail(value); }} /> : null}
      {dialog === "delete" && detail ? <DeleteDialog api={api} detail={detail} onClose={() => setDialog(null)} onDeleted={() => { setDialog(null); setSelectedId(""); void load(); }} /> : null}
    </section>
  );
}

function Metric({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return <div className={`admin-metric ${tone}`}><span>{label}:</span><strong>{value.toLocaleString()}</strong></div>;
}

function StatusPill({ value }: { value: string }) {
  return <span className={`admin-status-pill is-${value.replace(/_/g, "-")}`}>{value.replace(/_/g, " ")}</span>;
}

function QualityScore({ row }: { row: AdminBusinessSummary }) {
  const breakdown = row.data_quality_breakdown;
  const title = [
    `Validation ${breakdown.validation.points}/${breakdown.validation.max}`,
    `Provenance ${breakdown.provenance.points}/${breakdown.provenance.max}`,
    `Freshness ${breakdown.freshness.points}/${breakdown.freshness.max}`,
    `Resolution ${breakdown.resolution.points}/${breakdown.resolution.max}`,
    `Publication ${breakdown.publication.points}/${breakdown.publication.max}`,
    `${breakdown.fact_count} facts`,
    ...(breakdown.limitations || []),
  ].join(" · ");
  return (
    <span className={`admin-quality-score is-${row.data_quality_label}`} title={title}>
      <strong>{row.data_quality_score}</strong>
      <small>{row.data_quality_label}</small>
    </span>
  );
}

function BusinessInspector({
  api,
  detail,
  onEdit,
  onDelete,
  onRefresh,
}: {
  api: ApiClient;
  detail: AdminBusinessDetail | null;
  onEdit: () => void;
  onDelete: () => void;
  onRefresh: (value?: AdminBusinessDetail) => Promise<void>;
}) {
  const [tab, setTab] = useState<"validation" | "signals" | "facts" | "sources" | "history">("facts");
  const [busy, setBusy] = useState(false);
  const [lineage, setLineage] = useState<AdminFactLineage | null>(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [lineageError, setLineageError] = useState("");
  const loadLineage = useCallback(async () => {
    if (!detail?.id) {
      setLineage(null);
      return;
    }
    setLineageLoading(true);
    setLineageError("");
    try {
      setLineage(await api.getAdminBusinessFactLineage(detail.id));
    } catch (cause) {
      setLineageError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLineageLoading(false);
    }
  }, [api, detail?.id]);
  useEffect(() => {
    void loadLineage();
  }, [loadLineage]);
  if (!detail) return <aside className="admin-inspector is-empty">Select a business to inspect its evidence.</aside>;

  const runAction = async (action: "revalidate" | "status", status?: string) => {
    const reason = window.prompt(action === "revalidate" ? "Reason for revalidation" : `Reason for ${status}`);
    if (!reason?.trim()) return;
    setBusy(true);
    try {
      const result = action === "revalidate"
        ? await api.revalidateAdminBusiness(detail.id, reason)
        : await api.changeAdminBusinessStatus(detail.id, status || "active", reason);
      await onRefresh(result);
      await loadLineage();
    } finally {
      setBusy(false);
    }
  };

  const collectSignal = async (definitionId: string, label: string) => {
    const reason = window.prompt(`Reason for collecting ${label} for this business`);
    if (!reason?.trim()) return;
    setBusy(true);
    try {
      await api.collectAdminSignal(definitionId, reason, [detail.id]);
      await onRefresh();
      await loadLineage();
    } finally {
      setBusy(false);
    }
  };

  const validateSignal = async (definitionId: string, label: string, decision: "approve" | "reject") => {
    const reason = window.prompt(`Reason to ${decision} ${label} for this business`);
    if (!reason?.trim()) return;
    setBusy(true);
    try {
      await api.validateAdminSignal(definitionId, decision, reason, [detail.id]);
      await onRefresh();
      await loadLineage();
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="admin-inspector">
      <header>
        <div><h2>{detail.display_name}</h2><p>{detail.niche_label} · {detail.market_key}</p></div>
        <button className="admin-icon-button" title="Edit business" type="button" onClick={onEdit}><Pencil size={15} /></button>
      </header>
      <div className="admin-inspector-actions">
        <button disabled={busy} type="button" onClick={() => void runAction("revalidate")}><RefreshCw size={14} /> Revalidate</button>
        {detail.status === "active" ? (
          <button disabled={busy} type="button" onClick={() => void runAction("status", "quarantined")}><ShieldAlert size={14} /> Quarantine</button>
        ) : (
          <button disabled={busy} type="button" onClick={() => void runAction("status", "active")}><CheckCircle2 size={14} /> Restore</button>
        )}
        <button disabled={busy} type="button" onClick={() => void runAction("status", "archived")}><Archive size={14} /> Archive</button>
        <button className="danger" type="button" onClick={onDelete}><Trash2 size={14} /></button>
      </div>
      <dl className="admin-identity-grid">
        <div><dt>Website</dt><dd>{detail.website_url ? <a href={detail.website_url} target="_blank" rel="noreferrer">{detail.domain || detail.website_url}<ExternalLink size={12} /></a> : "Not stored"}</dd></div>
        <div><dt>Phone</dt><dd>{detail.phone || "Not stored"}</dd></div>
        <div><dt>Address</dt><dd>{detail.address || detail.geography || "Not stored"}</dd></div>
        <div><dt>Coordinates</dt><dd>{detail.latitude != null && detail.longitude != null ? `${detail.latitude}, ${detail.longitude}` : "Not stored"}</dd></div>
      </dl>
      <nav className="admin-tabs">
        {(["validation", "signals", "facts", "sources", "history"] as const).map((value) => <button className={tab === value ? "active" : ""} key={value} type="button" onClick={() => setTab(value)}>{value}</button>)}
      </nav>
      <div className="admin-inspector-content">
        {tab === "validation" ? detail.validations.map((item) => <article className="admin-validation-row" key={item.type}><div><strong>{item.type.replace(/_/g, " ")}</strong><StatusPill value={item.status} /></div><p>{item.reason}</p><small>{item.confidence}% confidence · {new Date(item.observed_at).toLocaleDateString()}</small></article>) : null}
        {tab === "signals" ? detail.signals.map((signal) => <article className="admin-signal-row" key={signal.definition_id}><div className="admin-signal-row-heading"><div><strong>{signal.label}</strong><small>{signal.category}{signal.quality_state ? ` · ${signal.quality_state}` : ""}</small></div><StatusPill value={signal.status} /></div><div className="admin-signal-row-value"><span>{signal.status === "missing" ? "No observation" : formatValue(signal.value)}{signal.unit && signal.value != null ? ` ${signal.unit}` : ""}</span><div className="admin-signal-row-actions">{signal.quality_state === "staged" ? <><button disabled={busy} type="button" onClick={() => void validateSignal(signal.definition_id, signal.label, "approve")}><CheckCircle2 size={13} /> Approve</button><button className="danger" disabled={busy} type="button" onClick={() => void validateSignal(signal.definition_id, signal.label, "reject")}><X size={13} /> Reject</button></> : null}<button disabled={busy} title={`Collect ${signal.label}`} type="button" onClick={() => void collectSignal(signal.definition_id, signal.label)}><Activity size={13} /> Collect</button></div></div>{signal.observed_at ? <small>{signal.confidence}% confidence · observed {new Date(signal.observed_at).toLocaleDateString()}</small> : null}</article>) : null}
        {tab === "facts" ? <FactLineageView lineage={lineage} loading={lineageLoading} error={lineageError} /> : null}
        {tab === "sources" ? detail.sources.map((source) => <article className="admin-source-row" key={String(source.id)}><div><strong>{String(source.provider)}</strong><StatusPill value={String(source.state)} /></div><p>{String(source.title || "Untitled source")}</p>{source.source_url ? <a href={String(source.source_url)} target="_blank" rel="noreferrer">Open evidence <ExternalLink size={12} /></a> : null}</article>) : null}
        {tab === "history" ? <KeyValueRows rows={detail.audit} primary="action" secondary="reason" /> : null}
      </div>
    </aside>
  );
}

function FactLineageView({
  lineage,
  loading,
  error,
}: {
  lineage: AdminFactLineage | null;
  loading: boolean;
  error: string;
}) {
  if (loading && !lineage) return <p className="admin-empty">Loading fact evidence…</p>;
  if (error) return <div className="admin-lineage-error"><strong>Fact evidence unavailable</strong><span>{error}</span></div>;
  if (!lineage?.facts.length) return <p className="admin-empty">No current facts for this business.</p>;
  const claims = new Map(lineage.claims.map((claim) => [claim.id, claim]));
  const observations = new Map(lineage.observations.map((observation) => [observation.id, observation]));
  return <div className="admin-fact-lineage-list">{lineage.facts.map((fact) => {
    const supportingClaims = fact.supporting_claim_ids
      .map((claimId) => claims.get(claimId))
      .filter((claim): claim is AdminFactLineageClaim => Boolean(claim));
    const missingClaimCount = fact.supporting_claim_ids.length - supportingClaims.length;
    const primaryObservation = fact.source_observation_id
      ? observations.get(fact.source_observation_id)
      : undefined;
    const claimObservationIds = new Set(supportingClaims.map((claim) => claim.source_observation_id));
    return (
      <details className="admin-fact-lineage" key={fact.id}>
        <summary>
          <div className="admin-fact-lineage-title">
            <strong>{humanizeKey(fact.key)}</strong>
            <span>{formatValue(fact.value)}</span>
          </div>
          <div className="admin-fact-lineage-state">
            <StatusPill value={fact.quality_state} />
            <small>{fact.confidence}%</small>
          </div>
        </summary>
        <div className="admin-fact-lineage-body">
          <dl className="admin-lineage-metadata">
            <div><dt>Resolution</dt><dd>{humanizeKey(fact.resolution_state)}</dd></div>
            <div><dt>Observed</dt><dd>{formatDate(fact.observed_at)}</dd></div>
            <div><dt>Fresh until</dt><dd>{fact.expires_at ? formatDate(fact.expires_at) : "Not bounded"}</dd></div>
          </dl>

          <section className="admin-lineage-section">
            <h4>Signal</h4>
            {fact.signal ? <>
              <div className="admin-lineage-signal-heading">
                <div><strong>{fact.signal.label}</strong><small>{humanizeKey(fact.signal.category)}</small></div>
                <StatusPill value={fact.signal.eligible_for_matching ? "opportunity" : fact.signal.matches_opportunity_value ? "ineligible" : "context"} />
              </div>
              <p>{fact.signal.eligible_for_matching
                ? "This published fact currently produces an eligible opportunity."
                : fact.signal.matches_opportunity_value
                  ? "The value represents an opportunity, but the fact is not currently eligible for matching."
                  : "The current value does not represent an opportunity."}</p>
              {fact.signal.services.length ? <div className="admin-lineage-services">{fact.signal.services.map((service) => <span key={service.id}>{service.label}</span>)}</div> : <small className="admin-lineage-muted">No service mapping.</small>}
            </> : <p>No signal definition is linked to this fact.</p>}
          </section>

          <section className="admin-lineage-section">
            <h4>Validation</h4>
            {fact.validation ? <>
              <div className="admin-lineage-validation-heading"><StatusPill value={fact.validation.status} /><span>{fact.validation.confidence}% confidence</span></div>
              <p>{fact.validation.reason}</p>
              <small className="admin-lineage-muted">{fact.validation.validator} · {formatDate(fact.validation.observed_at)}</small>
            </> : <p>No validation exists for this fact’s current observation.</p>}
          </section>

          <section className="admin-lineage-section">
            <h4>Supporting evidence <span>{supportingClaims.length} claim{supportingClaims.length === 1 ? "" : "s"}</span></h4>
            {supportingClaims.map((claim) => <FactClaimEvidence claim={claim} observation={observations.get(claim.source_observation_id)} key={claim.id} />)}
            {primaryObservation && !claimObservationIds.has(primaryObservation.id) ? <ObservationEvidence observation={primaryObservation} label="Primary observation" /> : null}
            {!supportingClaims.length && !primaryObservation ? <p>No supporting observation is linked.</p> : null}
            {missingClaimCount ? <p className="admin-lineage-warning">{missingClaimCount} supporting claim record{missingClaimCount === 1 ? " is" : "s are"} missing.</p> : null}
          </section>
        </div>
      </details>
    );
  })}</div>;
}

function FactClaimEvidence({
  claim,
  observation,
}: {
  claim: AdminFactLineageClaim;
  observation?: AdminFactLineageObservation;
}) {
  return <article className="admin-lineage-claim">
    <div><strong>{formatValue(claim.value)}</strong><span>{claim.confidence}% · {claim.extractor} v{claim.extractor_version}</span></div>
    <small>{formatDate(claim.observed_at)}</small>
    {observation ? <ObservationEvidence observation={observation} label="Source observation" /> : <p className="admin-lineage-warning">Source observation {claim.source_observation_id} is missing.</p>}
  </article>;
}

function ObservationEvidence({
  observation,
  label,
}: {
  observation: AdminFactLineageObservation;
  label: string;
}) {
  return <div className="admin-lineage-observation">
    <div><span>{label}</span><strong>{humanizeKey(observation.source)}</strong></div>
    <small>{formatDate(observation.observed_at)} · {observation.content_hash.slice(0, 10)}</small>
    {observation.source_url ? <a href={observation.source_url} target="_blank" rel="noreferrer">Open source <ExternalLink size={11} /></a> : null}
    <details className="admin-lineage-raw"><summary>Raw observation JSON</summary><pre>{JSON.stringify(observation.raw_payload, null, 2)}</pre></details>
  </div>;
}

function KeyValueRows({ rows, primary, secondary }: { rows: Array<Record<string, unknown>>; primary: string; secondary: string }) {
  if (!rows.length) return <p className="admin-empty">No records.</p>;
  return <>{rows.map((row, index) => <article className="admin-key-value-row" key={String(row.id || index)}><strong>{String(row[primary] ?? "-")}</strong><span>{formatValue(row[secondary])}</span>{row.confidence != null ? <small>{String(row.confidence)}% confidence</small> : null}</article>)}</>;
}

function formatValue(value: unknown) {
  if (value == null) return "Unknown";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function humanizeKey(value: string) {
  return value.replace(/_/g, " ");
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString();
}

function BusinessForm({ api, mode, detail, onClose, onSaved }: { api: ApiClient; mode: "add" | "edit"; detail?: AdminBusinessDetail; onClose: () => void; onSaved: (value: AdminBusinessDetail) => void }) {
  const [form, setForm] = useState<Record<string, string>>({
    display_name: detail?.display_name || "",
    niche_slug: detail?.niche_slug || "home_service_painting",
    market_key: detail?.market_key || "toronto",
    address: detail?.address || "",
    geography: detail?.geography || "",
    phone: detail?.phone || "",
    website_url: detail?.website_url || "",
    latitude: detail?.latitude == null ? "" : String(detail.latitude),
    longitude: detail?.longitude == null ? "" : String(detail.longitude),
    source_url: "",
    source_provider: "admin_manual",
    reason: "",
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const set = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const save = async () => {
    setSaving(true); setError("");
    try {
      const payload: Record<string, unknown> = { ...form };
      ["latitude", "longitude"].forEach((key) => { payload[key] = form[key] === "" ? null : Number(form[key]); });
      if (mode === "edit") { delete payload.niche_slug; delete payload.market_key; delete payload.source_url; delete payload.source_provider; }
      const result = mode === "add" ? await api.createAdminBusiness(payload) : await api.updateAdminBusiness(detail!.id, payload);
      onSaved(result);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setSaving(false); }
  };
  return <div className="admin-dialog-backdrop" role="presentation"><div className="admin-dialog" role="dialog" aria-modal="true"><header><div><h2>{mode === "add" ? "Add business" : "Edit business"}</h2><p>{mode === "add" ? "New records start quarantined until reviewed." : "Canonical changes quarantine the record and are written to audit history."}</p></div><button className="admin-icon-button" title="Close" type="button" onClick={onClose}><X size={16} /></button></header><div className="admin-form-grid"><Field label="Business name" value={form.display_name} onChange={(value) => set("display_name", value)} />{mode === "add" ? <><Field label="Niche slug" value={form.niche_slug} onChange={(value) => set("niche_slug", value)} /><Field label="Market key" value={form.market_key} onChange={(value) => set("market_key", value)} /></> : null}<Field label="Address" value={form.address} onChange={(value) => set("address", value)} /><Field label="Geography" value={form.geography} onChange={(value) => set("geography", value)} /><Field label="Phone" value={form.phone} onChange={(value) => set("phone", value)} /><Field label="Website" value={form.website_url} onChange={(value) => set("website_url", value)} /><Field label="Latitude" value={form.latitude} onChange={(value) => set("latitude", value)} /><Field label="Longitude" value={form.longitude} onChange={(value) => set("longitude", value)} />{mode === "add" ? <><Field label="Evidence URL" value={form.source_url} onChange={(value) => set("source_url", value)} /><Field label="Source provider" value={form.source_provider} onChange={(value) => set("source_provider", value)} /></> : null}<label className="full"><span>Reason</span><textarea value={form.reason} onChange={(event) => set("reason", event.target.value)} /></label></div>{error ? <div className="admin-error">{error}</div> : null}<footer><button type="button" onClick={onClose}>Cancel</button><button className="admin-primary-button" disabled={saving || !form.display_name.trim() || !form.reason.trim() || (mode === "add" && !form.source_url.trim())} type="button" onClick={() => void save()}>{saving ? "Saving..." : "Save"}</button></footer></div></div>;
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) { return <label><span>{label}</span><input value={value} onChange={(event) => onChange(event.target.value)} /></label>; }

function DeleteDialog({ api, detail, onClose, onDeleted }: { api: ApiClient; detail: AdminBusinessDetail; onClose: () => void; onDeleted: () => void }) {
  const [confirmation, setConfirmation] = useState(""); const [reason, setReason] = useState(""); const [error, setError] = useState(""); const [dependencyMap, setDependencyMap] = useState<Record<string, number> | null>(null);
  useEffect(() => { void api.getAdminBusinessDeleteDependencies(detail.id).then(setDependencyMap).catch((cause) => setError(cause instanceof Error ? cause.message : String(cause))); }, [api, detail.id]);
  const dependencies = useMemo(() => Object.entries(dependencyMap || {}), [dependencyMap]);
  const remove = async () => { try { await api.deleteAdminBusiness(detail.id, confirmation, reason); onDeleted(); } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); } };
  return <div className="admin-dialog-backdrop"><div className="admin-dialog admin-delete-dialog" role="dialog" aria-modal="true"><header><div><h2>Delete business permanently</h2><p>Use Archive for records that have evidence or workflow history.</p></div><button className="admin-icon-button" type="button" onClick={onClose}><X size={16} /></button></header>{dependencyMap === null ? <div className="admin-dependency-warning"><RefreshCw className="sl-spin-icon" size={16} /><div><strong>Checking related records</strong></div></div> : dependencies.length ? <div className="admin-dependency-warning"><CircleAlert size={16} /><div><strong>Permanent deletion is blocked</strong><p>{dependencies.map(([key, value]) => `${key}: ${value}`).join(" · ")}</p></div></div> : null}<Field label={`Type “${detail.display_name}”`} value={confirmation} onChange={setConfirmation} /><label><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>{error ? <div className="admin-error">{error}</div> : null}<footer><button type="button" onClick={onClose}>Cancel</button><button className="admin-danger-button" disabled={dependencyMap === null || Boolean(dependencies.length) || confirmation !== detail.display_name || !reason.trim()} type="button" onClick={() => void remove()}><Trash2 size={14} /> Delete permanently</button></footer></div></div>;
}
