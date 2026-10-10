import {
  Archive,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Database,
  ExternalLink,
  FileClock,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useAppData } from "../state/app-data";
import type {
  AdminBusinessDetail,
  AdminBusinessSummary,
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
  published: 0,
};

export function AdminDataScreen() {
  const { territoryApi } = useAppData();
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [overview, setOverview] = useState(emptyOverview);
  const [rows, setRows] = useState<AdminBusinessSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [validation, setValidation] = useState("");
  const [status, setStatus] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<AdminBusinessDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState<"add" | "edit" | "delete" | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      await territoryApi.getAdminAccess();
      setAllowed(true);
      const [summary, businessPage] = await Promise.all([
        territoryApi.getAdminOverview(),
        territoryApi.getAdminBusinesses({ q: search, validation, status, page, page_size: 50 }),
      ]);
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
  }, [page, search, status, territoryApi, validation]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 180);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (!selectedId || !allowed) {
      setDetail(null);
      return;
    }
    void territoryApi.getAdminBusiness(selectedId).then(setDetail).catch((cause) => {
      setError(cause instanceof Error ? cause.message : String(cause));
    });
  }, [allowed, selectedId, territoryApi]);

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

  return (
    <section className="admin-data-screen">
      <header className="admin-data-header">
        <div>
          <span className="admin-eyebrow">Data stewardship</span>
          <h1>Business quality</h1>
          <p>Inspect validation coverage, evidence, and publication readiness.</p>
        </div>
        <button className="admin-primary-button" type="button" onClick={() => setDialog("add")}>
          <Plus size={15} /> Add business
        </button>
      </header>

      <div className="admin-metrics" aria-label="Business quality overview">
        <Metric label="Businesses" value={overview.total} icon={<Database size={15} />} />
        <Metric label="Validated" value={overview.fully_validated} tone="good" icon={<CheckCircle2 size={15} />} />
        <Metric label="Needs attention" value={overview.needs_attention} tone="warn" icon={<CircleAlert size={15} />} />
        <Metric label="Incomplete" value={overview.incomplete} icon={<FileClock size={15} />} />
        <Metric label="Published" value={overview.published} icon={<CheckCircle2 size={15} />} />
      </div>

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
        <select aria-label="Validation state" value={validation} onChange={(event) => { setValidation(event.target.value); setPage(1); }}>
          <option value="">All validation</option>
          <option value="passed">Passed</option>
          <option value="attention">Needs attention</option>
          <option value="incomplete">Incomplete</option>
        </select>
        <select aria-label="Business state" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
          <option value="">All states</option>
          <option value="active">Active</option>
          <option value="quarantined">Quarantined</option>
          <option value="archived">Archived</option>
        </select>
        <button className="admin-icon-button" title="Refresh" type="button" onClick={() => void load()}>
          <RefreshCw size={15} />
        </button>
      </div>

      {error ? <div className="admin-error"><CircleAlert size={15} /> {error}</div> : null}

      <div className="admin-workspace">
        <div className="admin-table-pane">
          <table className="admin-business-table">
            <thead><tr><th>Business</th><th>Market</th><th>Validation</th><th>State</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr className={row.id === selectedId ? "is-selected" : ""} key={row.id} onClick={() => setSelectedId(row.id)}>
                  <td><strong>{row.display_name}</strong><span>{row.niche_label || "Unclassified"}</span></td>
                  <td><strong>{row.market_key || "Unknown"}</strong><span>{row.address || row.geography || "No address"}</span></td>
                  <td><StatusPill value={row.validation_state} /></td>
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
          detail={detail}
          onEdit={() => setDialog("edit")}
          onDelete={() => setDialog("delete")}
          onRefresh={refreshDetail}
        />
      </div>

      {dialog === "add" ? <BusinessForm mode="add" onClose={() => setDialog(null)} onSaved={(value) => { setDialog(null); void refreshDetail(value); }} /> : null}
      {dialog === "edit" && detail ? <BusinessForm mode="edit" detail={detail} onClose={() => setDialog(null)} onSaved={(value) => { setDialog(null); void refreshDetail(value); }} /> : null}
      {dialog === "delete" && detail ? <DeleteDialog detail={detail} onClose={() => setDialog(null)} onDeleted={() => { setDialog(null); setSelectedId(""); void load(); }} /> : null}
    </section>
  );
}

function Metric({ label, value, icon, tone = "" }: { label: string; value: number; icon: ReactNode; tone?: string }) {
  return <div className={`admin-metric ${tone}`}><span>{icon}{label}</span><strong>{value.toLocaleString()}</strong></div>;
}

function StatusPill({ value }: { value: string }) {
  return <span className={`admin-status-pill is-${value.replace(/_/g, "-")}`}>{value.replace(/_/g, " ")}</span>;
}

function BusinessInspector({
  detail,
  onEdit,
  onDelete,
  onRefresh,
}: {
  detail: AdminBusinessDetail | null;
  onEdit: () => void;
  onDelete: () => void;
  onRefresh: (value?: AdminBusinessDetail) => Promise<void>;
}) {
  const { territoryApi } = useAppData();
  const [tab, setTab] = useState<"validation" | "facts" | "sources" | "history">("validation");
  const [busy, setBusy] = useState(false);
  if (!detail) return <aside className="admin-inspector is-empty">Select a business to inspect its evidence.</aside>;

  const runAction = async (action: "revalidate" | "status", status?: string) => {
    const reason = window.prompt(action === "revalidate" ? "Reason for revalidation" : `Reason for ${status}`);
    if (!reason?.trim()) return;
    setBusy(true);
    try {
      const result = action === "revalidate"
        ? await territoryApi.revalidateAdminBusiness(detail.id, reason)
        : await territoryApi.changeAdminBusinessStatus(detail.id, status || "active", reason);
      await onRefresh(result);
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
        {(["validation", "facts", "sources", "history"] as const).map((value) => <button className={tab === value ? "active" : ""} key={value} type="button" onClick={() => setTab(value)}>{value}</button>)}
      </nav>
      <div className="admin-inspector-content">
        {tab === "validation" ? detail.validations.map((item) => <article className="admin-validation-row" key={item.type}><div><strong>{item.type.replace(/_/g, " ")}</strong><StatusPill value={item.status} /></div><p>{item.reason}</p><small>{item.confidence}% confidence · {new Date(item.observed_at).toLocaleDateString()}</small></article>) : null}
        {tab === "facts" ? <KeyValueRows rows={detail.facts} primary="key" secondary="value" /> : null}
        {tab === "sources" ? detail.sources.map((source) => <article className="admin-source-row" key={String(source.id)}><div><strong>{String(source.provider)}</strong><StatusPill value={String(source.state)} /></div><p>{String(source.title || "Untitled source")}</p>{source.source_url ? <a href={String(source.source_url)} target="_blank" rel="noreferrer">Open evidence <ExternalLink size={12} /></a> : null}</article>) : null}
        {tab === "history" ? <KeyValueRows rows={detail.audit} primary="action" secondary="reason" /> : null}
      </div>
    </aside>
  );
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

function BusinessForm({ mode, detail, onClose, onSaved }: { mode: "add" | "edit"; detail?: AdminBusinessDetail; onClose: () => void; onSaved: (value: AdminBusinessDetail) => void }) {
  const { territoryApi } = useAppData();
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
      const result = mode === "add" ? await territoryApi.createAdminBusiness(payload) : await territoryApi.updateAdminBusiness(detail!.id, payload);
      onSaved(result);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setSaving(false); }
  };
  return <div className="admin-dialog-backdrop" role="presentation"><div className="admin-dialog" role="dialog" aria-modal="true"><header><div><h2>{mode === "add" ? "Add business" : "Edit business"}</h2><p>{mode === "add" ? "New records start quarantined until reviewed." : "Canonical changes quarantine the record and are written to audit history."}</p></div><button className="admin-icon-button" title="Close" type="button" onClick={onClose}><X size={16} /></button></header><div className="admin-form-grid"><Field label="Business name" value={form.display_name} onChange={(value) => set("display_name", value)} />{mode === "add" ? <><Field label="Niche slug" value={form.niche_slug} onChange={(value) => set("niche_slug", value)} /><Field label="Market key" value={form.market_key} onChange={(value) => set("market_key", value)} /></> : null}<Field label="Address" value={form.address} onChange={(value) => set("address", value)} /><Field label="Geography" value={form.geography} onChange={(value) => set("geography", value)} /><Field label="Phone" value={form.phone} onChange={(value) => set("phone", value)} /><Field label="Website" value={form.website_url} onChange={(value) => set("website_url", value)} /><Field label="Latitude" value={form.latitude} onChange={(value) => set("latitude", value)} /><Field label="Longitude" value={form.longitude} onChange={(value) => set("longitude", value)} />{mode === "add" ? <><Field label="Evidence URL" value={form.source_url} onChange={(value) => set("source_url", value)} /><Field label="Source provider" value={form.source_provider} onChange={(value) => set("source_provider", value)} /></> : null}<label className="full"><span>Reason</span><textarea value={form.reason} onChange={(event) => set("reason", event.target.value)} /></label></div>{error ? <div className="admin-error">{error}</div> : null}<footer><button type="button" onClick={onClose}>Cancel</button><button className="admin-primary-button" disabled={saving || !form.display_name.trim() || !form.reason.trim() || (mode === "add" && !form.source_url.trim())} type="button" onClick={() => void save()}>{saving ? "Saving..." : "Save"}</button></footer></div></div>;
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) { return <label><span>{label}</span><input value={value} onChange={(event) => onChange(event.target.value)} /></label>; }

function DeleteDialog({ detail, onClose, onDeleted }: { detail: AdminBusinessDetail; onClose: () => void; onDeleted: () => void }) {
  const { territoryApi } = useAppData(); const [confirmation, setConfirmation] = useState(""); const [reason, setReason] = useState(""); const [error, setError] = useState(""); const [dependencyMap, setDependencyMap] = useState<Record<string, number> | null>(null);
  useEffect(() => { void territoryApi.getAdminBusinessDeleteDependencies(detail.id).then(setDependencyMap).catch((cause) => setError(cause instanceof Error ? cause.message : String(cause))); }, [detail.id, territoryApi]);
  const dependencies = useMemo(() => Object.entries(dependencyMap || {}), [dependencyMap]);
  const remove = async () => { try { await territoryApi.deleteAdminBusiness(detail.id, confirmation, reason); onDeleted(); } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); } };
  return <div className="admin-dialog-backdrop"><div className="admin-dialog admin-delete-dialog" role="dialog" aria-modal="true"><header><div><h2>Delete business permanently</h2><p>Use Archive for records that have evidence or workflow history.</p></div><button className="admin-icon-button" type="button" onClick={onClose}><X size={16} /></button></header>{dependencyMap === null ? <div className="admin-dependency-warning"><RefreshCw className="sl-spin-icon" size={16} /><div><strong>Checking related records</strong></div></div> : dependencies.length ? <div className="admin-dependency-warning"><CircleAlert size={16} /><div><strong>Permanent deletion is blocked</strong><p>{dependencies.map(([key, value]) => `${key}: ${value}`).join(" · ")}</p></div></div> : null}<Field label={`Type “${detail.display_name}”`} value={confirmation} onChange={setConfirmation} /><label><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>{error ? <div className="admin-error">{error}</div> : null}<footer><button type="button" onClick={onClose}>Cancel</button><button className="admin-danger-button" disabled={dependencyMap === null || Boolean(dependencies.length) || confirmation !== detail.display_name || !reason.trim()} type="button" onClick={() => void remove()}><Trash2 size={14} /> Delete permanently</button></footer></div></div>;
}
