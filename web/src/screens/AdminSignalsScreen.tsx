import { Activity, CheckCircle2, CircleAlert, Pause, Play, Plus, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApiClient } from "../api/client";
import type { AdminSignalDefinition, AdminSignalDefinitionInput } from "../types/domain";

export function AdminSignalsScreen({ api }: { api: ApiClient }) {
  const [signals, setSignals] = useState<AdminSignalDefinition[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await api.getAdminSignals();
      setSignals(next);
      setSelectedId((current) => next.some((signal) => signal.id === current) ? current : next[0]?.id || "");
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { void load(); }, [load]);
  const selected = signals.find((signal) => signal.id === selectedId) || null;
  const totals = useMemo(() => ({
    all: signals.length,
    active: signals.filter((signal) => signal.status === "active").length,
    draft: signals.filter((signal) => signal.status === "draft").length,
  }), [signals]);

  const changeStatus = async (status: "active" | "inactive") => {
    if (!selected) return;
    const reason = window.prompt(status === "active" ? "Reason for activating and collecting this signal" : "Reason for deactivating this signal");
    if (!reason?.trim()) return;
    setBusy(true); setError("");
    try { await api.changeAdminSignalStatus(selected.id, status, reason); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };

  const collect = async () => {
    if (!selected) return;
    const reason = window.prompt("Reason for collecting this signal across existing businesses");
    if (!reason?.trim()) return;
    setBusy(true); setError("");
    try { await api.collectAdminSignal(selected.id, reason); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };

  const validateStaged = async () => {
    if (!selected) return;
    const reason = window.prompt("Reason for approving all staged values for this signal");
    if (!reason?.trim()) return;
    setBusy(true); setError("");
    try { await api.validateAdminSignal(selected.id, "approve", reason); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };

  return <section className="admin-data-screen admin-signals-screen">
    <header className="admin-data-header admin-overview-header">
      <div className="admin-metrics admin-business-metrics" aria-label="Signal overview">
        <Metric label="Definitions" value={totals.all} />
        <Metric label="Active" value={totals.active} tone="good" />
        <Metric label="Draft" value={totals.draft} />
      </div>
      <button className="admin-primary-button" type="button" onClick={() => setShowCreate(true)}><Plus size={15} /> Add signal</button>
    </header>
    {error ? <div className="admin-error"><CircleAlert size={15} /> {error}</div> : null}
    <div className="admin-workspace admin-signals-workspace">
      <div className="admin-table-pane">
        <table className="admin-business-table admin-signals-table">
          <thead><tr><th>Signal</th><th>Category</th><th>Collector</th><th>Status</th></tr></thead>
          <tbody>
            {signals.map((signal) => <tr className={signal.id === selectedId ? "is-selected" : ""} key={signal.id} onClick={() => setSelectedId(signal.id)}><td><strong>{signal.label}</strong><span>{signal.key}</span></td><td><strong>{signal.category}</strong><span>{signal.value_type}{signal.unit ? ` · ${signal.unit}` : ""}</span></td><td><strong>{signal.collector_key || "Not assigned"}</strong><span>{signal.extractor_key || "No extractor"}</span></td><td><Status value={signal.status} /></td></tr>)}
            {!loading && !signals.length ? <tr><td className="admin-empty" colSpan={4}>No signal definitions.</td></tr> : null}
          </tbody>
        </table>
        <footer className="admin-pagination"><span>{signals.length} signals</span><button className="admin-icon-button" title="Refresh" type="button" onClick={() => void load()}><RefreshCw size={14} /></button></footer>
      </div>
      <aside className={`admin-inspector admin-signal-inspector${selected ? "" : " is-empty"}`}>
        {selected ? <>
          <header><div><h2>{selected.label}</h2><p>{selected.key} · version {selected.version}</p></div><Status value={selected.status} /></header>
          <div className="admin-inspector-actions">
            {selected.status === "active" ? <button disabled={busy} type="button" onClick={() => void collect()}><Activity size={14} /> Collect all</button> : <button disabled={busy || !selected.collector_key || !selected.extractor_key} type="button" onClick={() => void changeStatus("active")}><Play size={14} /> Activate and collect</button>}
            {selected.status === "active" ? <button disabled={busy} type="button" onClick={() => void validateStaged()}><CheckCircle2 size={14} /> Approve staged</button> : null}
            {selected.status === "active" ? <button disabled={busy} type="button" onClick={() => void changeStatus("inactive")}><Pause size={14} /> Deactivate</button> : null}
          </div>
          <dl className="admin-signal-details">
            <Detail label="Category" value={selected.category} />
            <Detail label="Value type" value={`${selected.value_type}${selected.unit ? ` (${selected.unit})` : ""}`} />
            <Detail label="Collector" value={selected.collector_key || "Not assigned"} />
            <Detail label="Extractor" value={selected.extractor_key || "Not assigned"} />
            <Detail label="Freshness" value={`${selected.freshness_days} days`} />
            <Detail label="Opportunity" value={selected.opportunity_direction.replace(/_/g, " ")} />
          </dl>
          {selected.description ? <p className="admin-signal-description">{selected.description}</p> : null}
        </> : null}
      </aside>
    </div>
    {showCreate ? <CreateSignalDialog api={api} onClose={() => setShowCreate(false)} onCreated={(signal) => { setShowCreate(false); setSelectedId(signal.id); void load(); }} /> : null}
  </section>;
}

function Metric({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return <div className={`admin-metric ${tone}`}><span>{label}:</span><strong>{value.toLocaleString()}</strong></div>;
}

function Status({ value }: { value: string }) {
  return <span className={`admin-status-pill is-${value}`}>{value}</span>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function CreateSignalDialog({ api, onClose, onCreated }: { api: ApiClient; onClose: () => void; onCreated: (signal: AdminSignalDefinition) => void }) {
  const [form, setForm] = useState<AdminSignalDefinitionInput>({ key: "", label: "", description: "", value_type: "boolean", category: "conversion", collector_key: "existing_observation", extractor_key: "payload_path", freshness_days: 30, opportunity_direction: "false_is_opportunity", config: {}, reason: "" });
  const [payloadPath, setPayloadPath] = useState("");
  const [opportunityThreshold, setOpportunityThreshold] = useState("");
  const [opportunityValues, setOpportunityValues] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const set = <K extends keyof AdminSignalDefinitionInput>(key: K, value: AdminSignalDefinitionInput[K]) => setForm((current) => ({ ...current, [key]: value }));
  const create = async () => {
    setSaving(true); setError("");
    const threshold = Number(opportunityThreshold);
    const config: Record<string, unknown> = {};
    if (payloadPath) config.payload_path = payloadPath;
    if (opportunityThreshold !== "" && Number.isFinite(threshold)) config.opportunity_threshold = threshold;
    if (opportunityValues.trim()) config.opportunity_values = opportunityValues.split(",").map((value) => value.trim()).filter(Boolean);
    try { onCreated(await api.createAdminSignal({ ...form, config })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); setSaving(false); }
  };
  return <div className="admin-dialog-backdrop">
    <div className="admin-dialog admin-signal-dialog" role="dialog" aria-modal="true">
      <header>
        <div><h2>Add observable signal</h2><p>Create the definition first. Collection starts when it is activated.</p></div>
        <button className="admin-icon-button" title="Close" type="button" onClick={onClose}><X size={16} /></button>
      </header>
      <div className="admin-form-grid">
        <Field label="Key" value={form.key} onChange={(value) => set("key", value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))} />
        <Field label="Label" value={form.label} onChange={(value) => set("label", value)} />
        <Field label="Category" value={form.category} onChange={(value) => set("category", value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))} />
        <label><span>Value type</span><select value={form.value_type} onChange={(event) => set("value_type", event.target.value as AdminSignalDefinitionInput["value_type"])}><option value="boolean">Boolean</option><option value="number">Number</option><option value="text">Text</option></select></label>
        <Field label="Unit" value={form.unit || ""} onChange={(value) => set("unit", value)} />
        <label><span>Collector</span><select value={form.collector_key} onChange={(event) => set("collector_key", event.target.value)}><option value="existing_observation">Existing observation</option><option value="website_http">Website HTTP</option><option value="website_dom">Website DOM</option><option value="google_places">Google Places</option><option value="domain_rdap">Domain RDAP</option></select></label>
        <Field label="Extractor" value={form.extractor_key || ""} onChange={(value) => set("extractor_key", value)} />
        <Field label="Payload path" value={payloadPath} onChange={setPayloadPath} />
        <Field label="Freshness days" type="number" value={String(form.freshness_days)} onChange={(value) => set("freshness_days", Number(value) || 30)} />
        <label><span>Opportunity rule</span><select value={form.opportunity_direction} onChange={(event) => set("opportunity_direction", event.target.value)}><option value="none">Supporting only</option><option value="false_is_opportunity">False is opportunity</option><option value="true_is_opportunity">True is opportunity</option><option value="lower_is_opportunity">Below threshold</option><option value="higher_is_opportunity">Above threshold</option><option value="missing_is_opportunity">Matching text values</option></select></label>
        {form.opportunity_direction === "lower_is_opportunity" || form.opportunity_direction === "higher_is_opportunity" ? <Field label="Opportunity threshold" type="number" value={opportunityThreshold} onChange={setOpportunityThreshold} /> : null}
        {form.opportunity_direction === "missing_is_opportunity" ? <Field label="Opportunity values (comma separated)" value={opportunityValues} onChange={setOpportunityValues} /> : null}
        <label className="full"><span>Description</span><textarea value={form.description} onChange={(event) => set("description", event.target.value)} /></label>
        <label className="full"><span>Reason</span><textarea value={form.reason} onChange={(event) => set("reason", event.target.value)} /></label>
      </div>
      {error ? <div className="admin-error">{error}</div> : null}
      <footer><button type="button" onClick={onClose}>Cancel</button><button className="admin-primary-button" disabled={saving || form.key.length < 2 || form.label.length < 2 || form.reason.length < 3} type="button" onClick={() => void create()}>{saving ? "Creating..." : "Create draft"}</button></footer>
    </div>
  </div>;
}

function Field({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return <label><span>{label}</span><input type={type} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}
