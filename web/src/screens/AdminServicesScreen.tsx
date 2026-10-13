import { Activity, CircleAlert, Pencil, Pause, Play, Plus, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApiClient } from "../api/client";
import type { AdminServiceDefinition, AdminServiceDefinitionInput, AdminSignalDefinition } from "../types/domain";

export function AdminServicesScreen({ api }: { api: ApiClient }) {
  const [services, setServices] = useState<AdminServiceDefinition[]>([]);
  const [signals, setSignals] = useState<AdminSignalDefinition[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [editing, setEditing] = useState<AdminServiceDefinition | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const [nextServices, nextSignals] = await Promise.all([api.getAdminServices(), api.getAdminSignals("active")]);
      setServices(nextServices); setSignals(nextSignals);
      setSelectedId((current) => nextServices.some((item) => item.id === current) ? current : nextServices[0]?.id || "");
      setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
  }, [api]);
  useEffect(() => { void load(); }, [load]);
  const selected = services.find((item) => item.id === selectedId) || null;
  const totals = useMemo(() => ({ all: services.length, active: services.filter((item) => item.status === "active").length, draft: services.filter((item) => item.status === "draft").length }), [services]);

  const status = async (value: "active" | "inactive") => {
    if (!selected) return;
    const reason = window.prompt(`Reason for ${value === "active" ? "activating" : "deactivating"} this service`);
    if (!reason?.trim()) return;
    setBusy(true);
    try { await api.changeAdminServiceStatus(selected.id, value, reason); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  const collect = async () => {
    if (!selected) return;
    const reason = window.prompt("Reason for collecting this service's signals across existing businesses");
    if (!reason?.trim()) return;
    setBusy(true);
    try { await api.collectAdminService(selected.id, reason); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };

  return <section className="admin-data-screen admin-signals-screen">
    <header className="admin-data-header admin-overview-header">
      <div className="admin-metrics admin-business-metrics" aria-label="Service overview">
        <Metric label="Definitions" value={totals.all} /><Metric label="Active" value={totals.active} tone="good" /><Metric label="Draft" value={totals.draft} />
      </div>
      <button className="admin-primary-button" type="button" onClick={() => setEditing(null)}><Plus size={15} /> Add service</button>
    </header>
    {error ? <div className="admin-error"><CircleAlert size={15} /> {error}</div> : null}
    <div className="admin-workspace admin-signals-workspace">
      <div className="admin-table-pane">
        <table className="admin-business-table admin-services-table"><thead><tr><th>Service</th><th>Signals</th><th>Status</th></tr></thead><tbody>
          {services.map((service) => <tr className={service.id === selectedId ? "is-selected" : ""} key={service.id} onClick={() => setSelectedId(service.id)}><td><strong>{service.label}</strong><span>{service.key}</span></td><td><strong>{service.signals.length}</strong><span>mapped observations</span></td><td><Status value={service.status} /></td></tr>)}
          {!services.length ? <tr><td className="admin-empty" colSpan={3}>No service definitions.</td></tr> : null}
        </tbody></table>
        <footer className="admin-pagination"><span>{services.length} services</span><button className="admin-icon-button" title="Refresh" type="button" onClick={() => void load()}><RefreshCw size={14} /></button></footer>
      </div>
      <aside className={`admin-inspector admin-signal-inspector${selected ? "" : " is-empty"}`}>
        {selected ? <><header><div><h2>{selected.label}</h2><p>{selected.key} · version {selected.version}</p></div><Status value={selected.status} /></header>
          <div className="admin-inspector-actions"><button disabled={busy} type="button" onClick={() => setEditing(selected)}><Pencil size={14} /> Edit</button>{selected.status !== "inactive" ? <button disabled={busy || !selected.signals.length} type="button" onClick={() => void collect()}><Activity size={14} /> Collect signals</button> : null}{selected.status === "active" ? <button disabled={busy} type="button" onClick={() => void status("inactive")}><Pause size={14} /> Deactivate</button> : <button disabled={busy || !selected.signals.length} type="button" onClick={() => void status("active")}><Play size={14} /> Activate</button>}</div>
          {selected.description ? <p className="admin-signal-description">{selected.description}</p> : null}
          <div className="admin-service-mappings">{selected.signals.map((signal) => <div key={signal.definition_id}><span><strong>{signal.label}</strong><small>{signal.key}</small></span><b>{signal.weight.toFixed(1)}x</b></div>)}</div>
        </> : null}
      </aside>
    </div>
    {editing !== undefined ? <ServiceDialog api={api} service={editing} signals={signals} onClose={() => setEditing(undefined)} onSaved={(saved) => { setEditing(undefined); setSelectedId(saved.id); void load(); }} /> : null}
  </section>;
}

function ServiceDialog({ api, service, signals, onClose, onSaved }: { api: ApiClient; service: AdminServiceDefinition | null; signals: AdminSignalDefinition[]; onClose: () => void; onSaved: (service: AdminServiceDefinition) => void }) {
  const existing = new Map(service?.signals.map((item) => [item.definition_id, item.weight]) || []);
  const [form, setForm] = useState<AdminServiceDefinitionInput>({ key: service?.key || "", label: service?.label || "", description: service?.description || "", sort_order: service?.sort_order || 0, mappings: [...existing].map(([signal_definition_id, weight]) => ({ signal_definition_id, weight })), reason: "" });
  const [saving, setSaving] = useState(false); const [error, setError] = useState("");
  const selected = new Map(form.mappings.map((item) => [item.signal_definition_id, item.weight]));
  const toggle = (id: string) => setForm((current) => ({ ...current, mappings: selected.has(id) ? current.mappings.filter((item) => item.signal_definition_id !== id) : [...current.mappings, { signal_definition_id: id, weight: 1 }] }));
  const weight = (id: string, value: number) => setForm((current) => ({ ...current, mappings: current.mappings.map((item) => item.signal_definition_id === id ? { ...item, weight: Math.min(10, Math.max(.1, value || 1)) } : item) }));
  const save = async () => { setSaving(true); setError(""); try { onSaved(service ? await api.updateAdminService(service.id, { label: form.label, description: form.description, sort_order: form.sort_order, mappings: form.mappings, reason: form.reason }) : await api.createAdminService(form)); } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); setSaving(false); } };
  return <div className="admin-dialog-backdrop"><div className="admin-dialog admin-service-dialog" role="dialog" aria-modal="true"><header><div><h2>{service ? "Edit service" : "Add service"}</h2><p>Map the service to observable signals used for lead ranking.</p></div><button className="admin-icon-button" title="Close" type="button" onClick={onClose}><X size={16} /></button></header>
    <div className="admin-form-grid"><label><span>Key</span><input disabled={Boolean(service)} value={form.key} onChange={(event) => setForm({ ...form, key: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} /></label><label><span>Label</span><input value={form.label} onChange={(event) => setForm({ ...form, label: event.target.value })} /></label><label><span>Display order</span><input min="0" type="number" value={form.sort_order} onChange={(event) => setForm({ ...form, sort_order: Number(event.target.value) || 0 })} /></label><label className="full"><span>Description</span><textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label></div>
    <div className="admin-service-signal-picker">{signals.map((signal) => <label key={signal.id}><input checked={selected.has(signal.id)} type="checkbox" onChange={() => toggle(signal.id)} /><span><strong>{signal.label}</strong><small>{signal.category} · {signal.key}</small></span>{selected.has(signal.id) ? <input aria-label={`${signal.label} weight`} min="0.1" max="10" step="0.1" type="number" value={selected.get(signal.id)} onChange={(event) => weight(signal.id, Number(event.target.value))} /> : null}</label>)}</div>
    <div className="admin-form-grid"><label className="full"><span>Reason</span><textarea value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} /></label></div>{error ? <div className="admin-error">{error}</div> : null}<footer><button type="button" onClick={onClose}>Cancel</button><button className="admin-primary-button" disabled={saving || form.key.length < 2 || form.label.length < 2 || form.reason.length < 3} type="button" onClick={() => void save()}>{saving ? "Saving..." : service ? "Save changes" : "Create draft"}</button></footer>
  </div></div>;
}

function Metric({ label, value, tone = "" }: { label: string; value: number; tone?: string }) { return <div className={`admin-metric ${tone}`}><span>{label}:</span><strong>{value}</strong></div>; }
function Status({ value }: { value: string }) { return <span className={`admin-status-pill is-${value}`}>{value}</span>; }
