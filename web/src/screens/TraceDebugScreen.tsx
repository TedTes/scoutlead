import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleX,
  Database,
  RefreshCw,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Card, StatusPill } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { RunDiagnostics, RunPipelineEvent, ToolCall } from "../types/domain";
import { statusTone } from "../utils/status";

type TraceDebugScreenProps = {
  onExit: () => void;
};

const stageLabels: Record<string, string> = {
  request: "Request",
  index_match: "Existing matches",
  background_discovery: "Background job",
  source_fetch: "Provider fetch",
  candidate_filter: "Candidate filter",
  opportunity_audit: "Opportunity audit",
  final_output: "Final output",
};

export function TraceDebugScreen({ onExit }: TraceDebugScreenProps) {
  const {
    territoryApi,
    discoveryRuns,
    selectedDiscoveryRunId,
    setSelectedDiscoveryRunId,
    refreshSnapshot,
    snapshot,
  } = useAppData();
  const urlRunId = useMemo(() => new URLSearchParams(window.location.search).get("run") || "", []);
  const [runId, setRunId] = useState(urlRunId || selectedDiscoveryRunId || discoveryRuns[0]?.id || "");
  const [diagnostics, setDiagnostics] = useState<RunDiagnostics | null>(null);
  const [diagnosticsError, setDiagnosticsError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const latestRun = snapshot.latestAgentRun || snapshot.trace?.latest_run || snapshot.trace?.runs?.[0];

  useEffect(() => {
    if (runId || !selectedDiscoveryRunId) return;
    setRunId(selectedDiscoveryRunId);
  }, [runId, selectedDiscoveryRunId]);

  useEffect(() => {
    if (!runId) return;
    setSelectedDiscoveryRunId(runId);
    let active = true;
    setRefreshing(true);
    setDiagnosticsError("");
    void Promise.all([
      refreshSnapshot(runId),
      territoryApi.getDiscoveryRunDiagnostics(runId).then((value) => {
        if (active) setDiagnostics(value);
      }),
    ])
      .catch((error: unknown) => {
        if (active) setDiagnosticsError(error instanceof Error ? error.message : "Unable to load run diagnostics.");
      })
      .finally(() => {
        if (active) setRefreshing(false);
      });
    return () => {
      active = false;
    };
  }, [refreshSnapshot, runId, setSelectedDiscoveryRunId, territoryApi]);

  const chooseRun = (nextRunId: string) => {
    setRunId(nextRunId);
    setDiagnostics(null);
    window.history.replaceState(null, "", nextRunId ? `/trace?run=${encodeURIComponent(nextRunId)}` : "/trace");
  };

  const refresh = async () => {
    if (!runId) return;
    setRefreshing(true);
    setDiagnosticsError("");
    try {
      const [, value] = await Promise.all([
        refreshSnapshot(runId),
        territoryApi.getDiscoveryRunDiagnostics(runId),
      ]);
      setDiagnostics(value);
    } catch (error) {
      setDiagnosticsError(error instanceof Error ? error.message : "Unable to load run diagnostics.");
    } finally {
      setRefreshing(false);
    }
  };

  const candidateEvents = diagnostics?.events.filter((event) => event.event_type === "candidate_decision") || [];
  const indexEvents = diagnostics?.events.filter((event) => event.event_type === "index_decision") || [];
  const operationalEvents = diagnostics?.events.filter((event) => !["candidate_decision", "index_decision"].includes(event.event_type)) || [];

  return (
    <div className="trace-debug-page run-inspector">
      <header className="inspector-header">
        <div>
          <span className="inspector-eyebrow">Diagnostics</span>
          <h1>Run inspector</h1>
          <p>Follow one search from its request through source fetching, filtering, auditing, and final output.</p>
        </div>
        <div className="card-actions">
          <button className="secondary" type="button" onClick={onExit}>Back</button>
          <button className="secondary" type="button" onClick={() => void refresh()} disabled={!runId || refreshing}>
            <RefreshCw className={refreshing ? "is-spinning" : ""} size={14} />
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </header>

      <div className="trace-toolbar inspector-toolbar">
        <label className="field">
          <span>Recent run</span>
          <select value={runId} onChange={(event) => chooseRun(event.target.value)}>
            <option value="">Select a run</option>
            {discoveryRuns.slice(0, 30).map((run) => (
              <option value={run.id} key={run.id}>
                {run.name || "Untitled search"} · {formatTime(run.created_at)} · {run.status}
              </option>
            ))}
          </select>
        </label>
        <div className="trace-run-summary">
          <span>Run ID</span>
          <strong>{runId || "-"}</strong>
        </div>
        {diagnostics ? (
          <StatusPill tone={diagnostics.retention === "exact" ? "green" : "amber"}>
            {diagnostics.retention === "exact" ? "Exact row history" : "Aggregate history"}
          </StatusPill>
        ) : null}
      </div>

      {diagnosticsError ? <div className="inspector-error"><AlertTriangle size={16} />{diagnosticsError}</div> : null}
      {!runId ? <p className="empty-copy">No discovery run selected.</p> : null}

      {diagnostics ? (
        <>
          <section className="pipeline-summary" aria-label="Pipeline totals">
            <PipelineMetric label="Requested" value={diagnostics.summary.requested} />
            <ArrowRight size={14} />
            <PipelineMetric label="Existing" value={diagnostics.summary.existing_matches} />
            <ArrowRight size={14} />
            <PipelineMetric label="Fetched" value={diagnostics.summary.fetched} />
            <ArrowRight size={14} />
            <PipelineMetric label="Accepted" value={diagnostics.summary.accepted} />
            <ArrowRight size={14} />
            <PipelineMetric label="Rejected" value={diagnostics.summary.rejected} />
            <ArrowRight size={14} />
            <PipelineMetric label="Final" value={diagnostics.summary.final} emphasis />
          </section>

          {diagnostics.caveats.length ? (
            <div className="inspector-notice">
              <AlertTriangle size={16} />
              <div>{diagnostics.caveats.map((caveat) => <p key={caveat}>{caveat}</p>)}</div>
            </div>
          ) : null}

          <Card title="Original request" meta={<StatusPill tone={statusTone(diagnostics.run_status)}>{diagnostics.run_status}</StatusPill>}>
            <div className="trace-request-response">
              <JsonPanel label="Request and parsed contract" value={diagnostics.request} />
              <JsonPanel label="Business-index segment" value={diagnostics.segment} />
            </div>
          </Card>

          <Card title="Source pipeline" meta={<span className="inspector-card-meta">{diagnostics.sources.length} configured requests</span>}>
            {diagnostics.sources.length ? (
              <div className="inspector-table-wrap">
                <table className="inspector-table">
                  <thead><tr><th>Provider / query</th><th>Status</th><th>Quota</th><th>Fetched</th><th>Accepted</th><th>Rejected</th><th>Final</th></tr></thead>
                  <tbody>
                    {diagnostics.sources.map((source) => (
                      <tr key={source.key}>
                        <td>
                          <strong>{source.provider_id}</strong>
                          <span>{source.query}</span>
                          <details><summary>Request / state</summary><JsonPanel label="Request" value={source.request} /><JsonPanel label="Recorded state" value={source.state} /></details>
                          {source.failure ? <em>{source.failure}</em> : null}
                        </td>
                        <td><StatusPill tone={source.failure ? "red" : "green"}>{source.status}</StatusPill></td>
                        <td>{source.quota}</td><td>{source.fetched_count}</td>
                        <td>{displayCount(source.accepted_count)}</td><td>{displayCount(source.rejected_count)}</td><td>{source.final_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="empty-copy">No provider plan was stored for this run.</p>}
          </Card>

          <Card title="Background jobs" meta={<span className="inspector-card-meta">{diagnostics.jobs.length}</span>}>
            {diagnostics.jobs.length ? <div className="trace-stack">{diagnostics.jobs.map((job) => (
              <article className="trace-call compact" key={job.id}>
                <header><div><strong>{job.id}</strong><span>{job.type} · attempt {job.attempts}/{job.max_attempts}</span></div><StatusPill tone={statusTone(job.status)}>{job.status}</StatusPill></header>
                {job.last_error ? <p className="trace-error">{job.last_error}</p> : null}
                <JsonPanel label="Job payload" value={job.payload} />
              </article>
            ))}</div> : <p className="empty-copy">No background job is linked to this run.</p>}
          </Card>

          <Card title="Provider filtering decisions" meta={<span className="inspector-card-meta">{candidateEvents.length} retained rows</span>}>
            {candidateEvents.length ? <DecisionLedger events={candidateEvents} /> : <p className="empty-copy">Individual source rows were not retained for this run.</p>}
          </Card>

          <Card title="Index matching decisions" meta={<span className="inspector-card-meta">{indexEvents.length} evaluated businesses</span>}>
            {indexEvents.length ? <DecisionLedger events={indexEvents} /> : <p className="empty-copy">No per-business index decisions were retained for this run.</p>}
          </Card>

          <Card title="Final output" meta={<span className="inspector-card-meta">{diagnostics.final_results.length} leads</span>}>
            {diagnostics.final_results.length ? (
              <div className="inspector-table-wrap"><table className="inspector-table final-output-table"><thead><tr><th>Business</th><th>Source</th><th>Website</th><th>Status</th></tr></thead><tbody>
                {diagnostics.final_results.map((result) => <tr key={result.id}><td><strong>{result.company_name}</strong><span>{result.geography || "No geography"}</span></td><td>{result.source}</td><td>{result.website_url || "No website stored"}</td><td><StatusPill tone={statusTone(result.status)}>{result.status}</StatusPill></td></tr>)}
              </tbody></table></div>
            ) : <p className="empty-copy">This run produced no final leads.</p>}
          </Card>

          <Card title="Pipeline events" meta={<span className="inspector-card-meta">{operationalEvents.length}</span>}>
            <div className="trace-step-list">
              {operationalEvents.map((event) => <PipelineEventRow event={event} key={event.id} />)}
            </div>
          </Card>

          {latestRun ? <LegacyTrace runId={latestRun.id} steps={latestRun.steps || []} toolCalls={latestRun.tool_calls || []} /> : null}
        </>
      ) : null}
    </div>
  );
}

function PipelineMetric({ label, value, emphasis = false }: { label: string; value?: number | null; emphasis?: boolean }) {
  return <div className={emphasis ? "pipeline-metric emphasis" : "pipeline-metric"}><span>{label}</span><strong>{displayCount(value)}</strong></div>;
}

function DecisionLedger({ events }: { events: RunPipelineEvent[] }) {
  return <div className="decision-ledger">{events.map((event) => {
    const response = event.response_payload || {};
    const title = String(response.title || response.company_name || event.item_key || "Untitled result");
    const url = typeof response.url === "string" ? response.url : "";
    return <details className={`decision-row ${event.status}`} key={event.id}>
      <summary>
        {event.status === "accepted" ? <CheckCircle2 size={15} /> : <CircleX size={15} />}
        <span><strong>{title}</strong><small>{event.provider_id || "unknown source"}{url ? ` · ${url}` : ""}</small></span>
        <StatusPill tone={event.status === "accepted" ? "green" : "red"}>{event.status}</StatusPill>
      </summary>
      <p>{event.reason || "No reason recorded."}</p>
      <JsonPanel label="Fetched row" value={event.response_payload} />
    </details>;
  })}</div>;
}

function PipelineEventRow({ event }: { event: RunPipelineEvent }) {
  return <article className="trace-step">
    <Database size={15} />
    <div><strong>{stageLabels[event.stage] || event.stage}</strong><p>{event.event_type}{event.provider_id ? ` · ${event.provider_id}` : ""} · {formatTime(event.created_at)}</p>{event.reason ? <em>{event.reason}</em> : null}<details><summary>Input / output</summary><div className="trace-request-response"><JsonPanel label="Input" value={event.request_payload} /><JsonPanel label="Output" value={event.response_payload} /></div></details></div>
    <StatusPill tone={statusTone(event.status)}>{event.status}</StatusPill>
  </article>;
}

function LegacyTrace({ runId, steps, toolCalls }: { runId: string; steps: Array<{ id: string; phase: string; status: string; objective: string; error?: string | null }>; toolCalls: ToolCall[] }) {
  return <details className="legacy-trace"><summary>Legacy agent trace · {runId}</summary><div className="trace-stack">{steps.map((step) => <article className="trace-step" key={step.id}><Database size={15} /><div><strong>{step.phase}</strong><p>{step.objective}</p>{step.error ? <em>{step.error}</em> : null}</div><StatusPill tone={statusTone(step.status)}>{step.status}</StatusPill></article>)}{toolCalls.map((call) => <article className="trace-call compact" key={call.id}><header><div><strong>{call.tool_name}</strong><span>{call.reason || "No reason recorded"}</span></div><StatusPill tone={statusTone(call.status)}>{call.status}</StatusPill></header>{call.error ? <p className="trace-error">{call.error}</p> : null}<div className="trace-request-response"><JsonPanel label="Request" value={call.args} /><JsonPanel label="Response" value={call.observation ?? call.error ?? null} /></div></article>)}</div></details>;
}

function JsonPanel({ label, value }: { label: string; value: unknown }) {
  return <details className="trace-json-panel"><summary>{label}</summary><pre>{formatJson(redact(value))}</pre></details>;
}

function displayCount(value?: number | null) { return value === null || value === undefined ? "-" : String(value); }
function formatTime(value: string) { return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value)); }
function formatJson(value: unknown) { if (value === undefined) return "undefined"; if (typeof value === "string") return value; return JSON.stringify(value, null, 2); }
function redact(value: unknown): unknown { if (Array.isArray(value)) return value.map(redact); if (!value || typeof value !== "object") return value; return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, entry]) => [key, shouldRedactKey(key) ? "[redacted]" : redact(entry)])); }
function shouldRedactKey(key: string) { return /(api[_-]?key|authorization|bearer|password|secret|token)/i.test(key); }
