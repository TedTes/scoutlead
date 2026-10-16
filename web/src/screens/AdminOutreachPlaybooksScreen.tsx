import { Activity, CheckCircle2, RefreshCw, Save } from "lucide-react";
import { useEffect, useState } from "react";

import type { ApiClient } from "../api/client";
import type { AdminOutreachPlaybook, OutreachAnalytics } from "../types/domain";


export function AdminOutreachPlaybooksScreen({ api }: { api: ApiClient }) {
  const [playbooks, setPlaybooks] = useState<AdminOutreachPlaybook[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [json, setJson] = useState("");
  const [reason, setReason] = useState("");
  const [analytics, setAnalytics] = useState<OutreachAnalytics | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setError("");
    try {
      const [nextPlaybooks, nextAnalytics] = await Promise.all([
        api.getAdminOutreachPlaybooks(),
        api.getOutreachAnalytics(),
      ]);
      setPlaybooks(nextPlaybooks);
      setAnalytics(nextAnalytics);
      const key = selectedKey || nextPlaybooks[0]?.service_key || "";
      const selected = nextPlaybooks.find((item) => item.service_key === key);
      setSelectedKey(key);
      if (selected) setJson(JSON.stringify(selected.definition, null, 2));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  useEffect(() => { void load(); }, []);

  const select = (playbook: AdminOutreachPlaybook) => {
    setSelectedKey(playbook.service_key);
    setJson(JSON.stringify(playbook.definition, null, 2));
    setReason("");
    setError("");
  };

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const definition = JSON.parse(json) as Record<string, unknown>;
      const updated = await api.updateAdminOutreachPlaybook(selectedKey, definition, reason);
      setPlaybooks((current) => current.map((item) => item.service_key === selectedKey ? updated : item));
      setReason("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const changeStatus = async (status: "active" | "inactive") => {
    setBusy(true);
    setError("");
    try {
      const updated = await api.changeAdminOutreachPlaybookStatus(selectedKey, status, reason);
      setPlaybooks((current) => current.map((item) => item.service_key === selectedKey ? updated : item));
      setReason("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const selected = playbooks.find((item) => item.service_key === selectedKey);
  return (
    <section className="admin-data-screen admin-playbooks-screen">
      <header className="admin-data-header admin-overview-header">
        <div className="admin-metrics" aria-label="Outreach activity">
          <Metric label="Events" value={analytics?.total_events || 0} />
          <Metric label="Copies" value={analytics?.by_event.draft_copied || 0} />
          <Metric label="Replies" value={analytics?.by_event.response_classified || 0} />
          <Metric label="Meetings" value={analytics?.by_event.meeting_booked || 0} />
        </div>
        <button className="admin-icon-button" title="Refresh" type="button" onClick={() => void load()}><RefreshCw size={14} /></button>
      </header>
      {error ? <div className="admin-error">{error}</div> : null}
      <div className="admin-workspace admin-playbook-workspace">
        <div className="admin-table-pane">
          <table className="admin-business-table"><thead><tr><th>Playbook</th><th>Version</th><th>Status</th></tr></thead><tbody>
            {playbooks.map((item) => <tr className={item.service_key === selectedKey ? "selected" : ""} key={item.service_key} onClick={() => select(item)}><td>{item.service_key.replace(/_/g, " ")}</td><td>{item.version}</td><td><span className={`admin-status-pill is-${item.status}`}>{item.status}</span></td></tr>)}
          </tbody></table>
        </div>
        <aside className="admin-inspector admin-playbook-editor">
          {selected ? <>
            <header><div><strong>{selected.service_key.replace(/_/g, " ")}</strong><small>Validated JSON override</small></div><span className={`admin-status-pill is-${selected.status}`}>{selected.status}</span></header>
            <label><span>Definition</span><textarea spellCheck={false} value={json} onChange={(event) => setJson(event.target.value)} /></label>
            <label><span>Change reason</span><input value={reason} onChange={(event) => setReason(event.target.value)} /></label>
            <div className="admin-inspector-actions">
              <button disabled={busy || reason.trim().length < 3} type="button" onClick={() => void save()}><Save size={14} /> Save draft</button>
              <button className="admin-primary-button" disabled={busy || reason.trim().length < 3} type="button" onClick={() => void changeStatus("active")}><CheckCircle2 size={14} /> Activate</button>
              <button disabled={busy || reason.trim().length < 3} type="button" onClick={() => void changeStatus("inactive")}><Activity size={14} /> Deactivate</button>
            </div>
          </> : <p className="admin-empty">Select a playbook.</p>}
        </aside>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="admin-metric"><span>{label}:</span><strong>{value.toLocaleString()}</strong></div>;
}
