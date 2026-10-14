import {
  Ban,
  CheckCircle2,
  CircleAlert,
  ExternalLink,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApiClient } from "../api/client";
import type { AdminDataJob, AdminDataSegment } from "../types/domain";

export function AdminDataJobsScreen({ api }: { api: ApiClient }) {
  const [jobs, setJobs] = useState<AdminDataJob[]>([]);
  const [segments, setSegments] = useState<AdminDataSegment[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<AdminDataJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextJobs, nextSegments] = await Promise.all([
        api.getAdminDataJobs(),
        api.getAdminDataSegments(),
      ]);
      setJobs(nextJobs);
      setSegments(nextSegments);
      setError("");
      setSelectedId((current) => nextJobs.some((job) => job.id === current) ? current : nextJobs[0]?.id || "");
    } catch (cause) {
      setError(dataJobError(cause));
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { void load(); }, [load]);
  const hasActiveJobs = jobs.some((job) => (
    ["queued", "collecting", "validating", "validating_sample"].includes(job.status)
  ));
  useEffect(() => {
    if (!hasActiveJobs || error) return undefined;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [error, hasActiveJobs, load]);
  useEffect(() => {
    if (!selectedId) { setDetail(null); return; }
    void api.getAdminDataJob(selectedId).then(setDetail).catch((cause) => {
      setError(dataJobError(cause));
    });
  }, [api, jobs, selectedId]);

  const totals = useMemo(() => ({
    items: jobs.reduce((sum, job) => sum + job.total_items, 0),
    review: jobs.filter((job) => ["awaiting_review", "sample_ready"].includes(job.status)).length,
    active: jobs.filter((job) => ["queued", "collecting", "validating", "validating_sample"].includes(job.status)).length,
    failed: jobs.filter((job) => job.status === "failed").length,
  }), [jobs]);

  const refresh = async (result?: AdminDataJob) => {
    if (result) setDetail(result);
    await load();
  };

  const action = async (kind: "selected" | "all" | "discard" | "cancel" | "retry", sourceItemIds: string[] = []) => {
    if (!detail) return;
    const labels = {
      selected: `Reason for resolving ${sourceItemIds.length} selected sources`,
      all: "Reason for resolving all remaining items",
      discard: "Reason for discarding the remaining staged items",
      cancel: "Reason for canceling queued collection work",
      retry: "Reason for retrying failed collection work",
    };
    const reason = window.prompt(labels[kind]);
    if (!reason?.trim()) return;
    setBusy(true); setError("");
    try {
      const result = kind === "selected"
        ? await api.validateAdminDataJob(detail.id, reason, sourceItemIds)
        : kind === "all"
          ? await api.validateAdminDataJob(detail.id, reason)
          : kind === "discard"
            ? await api.discardAdminDataJob(detail.id, reason)
            : kind === "cancel"
              ? await api.cancelAdminDataJob(detail.id, reason)
              : await api.retryAdminDataJob(detail.id, reason);
      await refresh(result);
    } catch (cause) {
      setError(dataJobError(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="admin-data-screen">
      <header className="admin-data-header admin-overview-header">
        <div className="admin-metrics admin-job-metrics" aria-label="Source fetch overview">
          <Metric label="Returned sources" value={totals.items} />
          <Metric label="Active fetches" value={totals.active} />
          <Metric label="Awaiting review" value={totals.review} tone="warn" />
          <Metric label="Failed fetches" value={totals.failed} tone={totals.failed ? "bad" : "good"} />
        </div>
        <button className="admin-primary-button" type="button" onClick={() => setShowCreate(true)}>
          <Play size={15} /> Fetch sources
        </button>
      </header>

      {error ? <div className="admin-error"><CircleAlert size={15} /> {error}</div> : null}

      <div className="admin-workspace admin-jobs-workspace">
        <div className="admin-table-pane">
          <table className="admin-business-table admin-jobs-table">
            <thead><tr><th>Fetch</th><th>Mode</th><th>Sources</th><th>Status</th></tr></thead>
            <tbody>
              {jobs.map((job) => (
                <tr className={job.id === selectedId ? "is-selected" : ""} key={job.id} onClick={() => setSelectedId(job.id)}>
                  <td><strong>{job.segment_label}</strong><span>{new Date(job.created_at).toLocaleString()}</span></td>
                  <td><strong>{job.processing_mode === "review_first" ? "Review first" : "Automatic"}</strong><span>{job.reason || "No reason recorded"}</span></td>
                  <td><strong>{job.total_items.toLocaleString()}</strong><span>{job.businesses_created} businesses</span></td>
                  <td><JobPill value={job.status} /></td>
                </tr>
              ))}
              {!loading && !jobs.length ? <tr><td className="admin-empty" colSpan={4}>No sources fetched yet.</td></tr> : null}
            </tbody>
          </table>
          <footer className="admin-pagination">
            <span>{jobs.length} fetches</span>
            <button className="admin-icon-button" title="Refresh" type="button" onClick={() => void load()}><RefreshCw size={14} /></button>
          </footer>
        </div>
        <JobInspector detail={detail} busy={busy} onAction={action} />
      </div>

      {showCreate ? <CreateDataJobDialog api={api} segments={segments} onClose={() => setShowCreate(false)} onCreated={(job) => { setShowCreate(false); setSelectedId(job.id); void refresh(job); }} /> : null}
    </section>
  );
}

function Metric({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return <div className={`admin-metric ${tone}`}><span>{label}:</span><strong>{value.toLocaleString()}</strong></div>;
}

function JobPill({ value }: { value: string }) {
  return <span className={`admin-status-pill is-${value.replace(/_/g, "-")}`}>{value.replace(/_/g, " ")}</span>;
}

function JobInspector({ detail, busy, onAction }: { detail: AdminDataJob | null; busy: boolean; onAction: (kind: "selected" | "all" | "discard" | "cancel" | "retry", sourceItemIds?: string[]) => Promise<void> }) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  useEffect(() => { setSelectedIds([]); }, [detail?.id]);
  if (!detail) return <aside className="admin-inspector is-empty">Select a fetch to inspect its returned sources.</aside>;
  const canReview = detail.processing_mode === "review_first" && detail.pending_review > 0 && ["awaiting_review", "sample_ready"].includes(detail.status);
  const canCancel = ["queued", "collecting"].includes(detail.status);
  const sourceItems = detail.source_items || [];
  const selectableIds = sourceItems.filter((item) => ["fetched", "relevant"].includes(item.state)).map((item) => item.id);
  const allDisplayedSelected = selectableIds.length > 0 && selectableIds.every((id) => selectedIds.includes(id));
  const toggle = (id: string) => setSelectedIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  return (
    <aside className="admin-inspector admin-job-inspector">
      <header><div><h2>{detail.segment_label}</h2><p>{detail.processing_mode === "review_first" ? "Review before indexing" : "Automatic indexing"}</p></div><JobPill value={detail.status} /></header>
      <div className="admin-inspector-actions">
        {canReview ? <button disabled={busy || !selectedIds.length} type="button" onClick={() => void onAction("selected", selectedIds)}><ShieldCheck size={14} /> Index selected ({selectedIds.length})</button> : null}
        {canReview ? <button disabled={busy} type="button" onClick={() => void onAction("all")}><CheckCircle2 size={14} /> Index all</button> : null}
        {detail.status === "failed" ? <button disabled={busy} type="button" onClick={() => void onAction("retry")}><RotateCcw size={14} /> Retry failed</button> : null}
        {canCancel ? <button disabled={busy} type="button" onClick={() => void onAction("cancel")}><Ban size={14} /> Cancel</button> : null}
        {canReview ? <button className="danger" disabled={busy} type="button" onClick={() => void onAction("discard")}><Trash2 size={14} /> Discard staged</button> : null}
      </div>
      <div className="admin-job-summary-grid">
        <Summary label="Collected" value={detail.total_items} />
        <Summary label="Awaiting review" value={detail.pending_review} />
        <Summary label="Processing" value={detail.processing} />
        <Summary label="Indexed" value={detail.validated} />
        <Summary label="Needs attention" value={detail.needs_attention} />
        <Summary label="Businesses created" value={detail.businesses_created} />
      </div>
      <section className="admin-job-breakdown">
        <h3>Source coverage</h3>
        <div className="admin-job-source-list">
          {Object.entries(detail.source_counts).map(([source, count]) => <div key={source}><span>{source}</span><strong>{count}</strong></div>)}
          {!Object.keys(detail.source_counts).length ? <p>No source items collected yet.</p> : null}
        </div>
        <h3>Field completeness</h3>
        <div className="admin-job-completeness">
          {Object.entries(detail.completeness).map(([field, count]) => <div key={field}><span>{field.replace(/^with_/, "").replace(/_/g, " ")}</span><strong>{detail.total_items ? Math.round((count / detail.total_items) * 100) : 0}%</strong></div>)}
        </div>
      </section>
      <section className="admin-job-samples admin-source-results">
        <div className="admin-source-results-header">
          <label><input checked={allDisplayedSelected} disabled={!canReview || !selectableIds.length} type="checkbox" onChange={() => setSelectedIds(allDisplayedSelected ? [] : selectableIds)} /> Select returned sources</label>
          <span>{sourceItems.length} of {detail.total_items}</span>
        </div>
        {sourceItems.map((item) => <article key={item.id}><input aria-label={`Select ${item.title || "source"}`} checked={selectedIds.includes(item.id)} disabled={!canReview || !selectableIds.includes(item.id)} type="checkbox" onChange={() => toggle(item.id)} /><div className="admin-source-result-main"><div><strong>{item.title || "Untitled source item"}</strong><JobPill value={item.state} /></div><p>{[item.provider, item.address, item.phone, item.website].filter(Boolean).join(" · ")}</p>{item.source_url ? <a href={item.source_url} rel="noreferrer" target="_blank">Open source <ExternalLink size={11} /></a> : null}</div></article>)}
        {detail.source_items_truncated ? <p className="admin-source-limit">Showing the first 200 sources. Index all applies to every returned source.</p> : null}
        {!sourceItems.length ? <p className="admin-empty">Returned sources appear here after fetching.</p> : null}
      </section>
      {detail.errors.length ? <div className="admin-error"><CircleAlert size={15} /><div>{detail.errors.map((value) => <p key={value}>{value}</p>)}</div></div> : null}
    </aside>
  );
}

function Summary({ label, value }: { label: string; value: number }) {
  return <div><span>{label}</span><strong>{value.toLocaleString()}</strong></div>;
}

function CreateDataJobDialog({ api, segments, onClose, onCreated }: { api: ApiClient; segments: AdminDataSegment[]; onClose: () => void; onCreated: (job: AdminDataJob) => void }) {
  const activeSegments = segments.filter((segment) => segment.status === "active");
  const [segmentId, setSegmentId] = useState(activeSegments[0]?.id || "");
  const [mode, setMode] = useState<"automatic" | "review_first">("review_first");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const create = async () => {
    setSaving(true); setError("");
    try { onCreated(await api.createAdminDataJob({ segment_id: segmentId, processing_mode: mode, reason })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); setSaving(false); }
  };
  return <div className="admin-dialog-backdrop"><div className="admin-dialog admin-data-job-dialog" role="dialog" aria-modal="true"><header><div><h2>Fetch sources</h2><p>Fetch business records now, then optionally review them before indexing.</p></div><button className="admin-icon-button" title="Close" type="button" onClick={onClose}><X size={16} /></button></header><div className="admin-data-job-form"><label><span>Business segment</span><select value={segmentId} onChange={(event) => setSegmentId(event.target.value)}>{activeSegments.map((segment) => <option key={segment.id} value={segment.id}>{segment.niche_label} · {segment.market_label} · {segment.source_count} sources</option>)}</select></label><fieldset><legend>After fetching</legend><label><input checked={mode === "review_first"} name="mode" type="radio" onChange={() => setMode("review_first")} /><span><strong>Review returned sources</strong><small>Choose selected sources or all sources to index.</small></span></label><label><input checked={mode === "automatic"} name="mode" type="radio" onChange={() => setMode("automatic")} /><span><strong>Index automatically</strong><small>Resolve businesses, index them, then collect signals.</small></span></label></fieldset><label><span>Reason</span><textarea placeholder="What sources are you fetching and why?" value={reason} onChange={(event) => setReason(event.target.value)} /></label></div>{error ? <div className="admin-error">{error}</div> : null}<footer><button type="button" onClick={onClose}>Cancel</button><button className="admin-primary-button" disabled={saving || !segmentId || reason.trim().length < 3} type="button" onClick={() => void create()}>{saving ? "Fetching..." : "Fetch sources"}</button></footer></div></div>;
}

function dataJobError(cause: unknown) {
  const message = cause instanceof Error ? cause.message : String(cause);
  return /404/.test(message)
    ? "Source fetching API is unavailable (404). Deploy the API service containing the new admin source endpoints."
    : message;
}
