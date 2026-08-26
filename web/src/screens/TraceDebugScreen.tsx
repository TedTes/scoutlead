import { RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Card, StatusPill } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { ToolCall } from "../types/domain";
import type { Tone } from "../types/navigation";
import { statusTone } from "../utils/status";

type TraceDebugScreenProps = {
  onExit: () => void;
};

export function TraceDebugScreen({ onExit }: TraceDebugScreenProps) {
  const {
    discoveryRuns,
    selectedDiscoveryRunId,
    setSelectedDiscoveryRunId,
    refreshSnapshot,
    snapshot,
  } = useAppData();
  const urlRunId = useMemo(() => new URLSearchParams(window.location.search).get("run") || "", []);
  const [runId, setRunId] = useState(urlRunId || selectedDiscoveryRunId || discoveryRuns[0]?.id || "");
  const [refreshing, setRefreshing] = useState(false);
  const selectedRun = discoveryRuns.find((run) => run.id === runId) || snapshot.run;
  const trace = snapshot.trace;
  const latestRun = snapshot.latestAgentRun || trace?.latest_run || trace?.runs?.[0];
  const toolCalls = latestRun?.tool_calls || [];
  const steps = latestRun?.steps || [];

  useEffect(() => {
    if (runId || !selectedDiscoveryRunId) return;
    setRunId(selectedDiscoveryRunId);
  }, [runId, selectedDiscoveryRunId]);

  useEffect(() => {
    if (!runId) return;
    if (runId !== selectedDiscoveryRunId) {
      setSelectedDiscoveryRunId(runId);
    }
    void refreshSnapshot(runId);
  }, [refreshSnapshot, runId, selectedDiscoveryRunId, setSelectedDiscoveryRunId]);

  const chooseRun = async (nextRunId: string) => {
    setRunId(nextRunId);
    setSelectedDiscoveryRunId(nextRunId);
    window.history.replaceState(null, "", nextRunId ? `/trace?run=${encodeURIComponent(nextRunId)}` : "/trace");
    if (nextRunId) {
      setRefreshing(true);
      try {
        await refreshSnapshot(nextRunId);
      } finally {
        setRefreshing(false);
      }
    }
  };

  const refresh = async () => {
    if (!runId) return;
    setRefreshing(true);
    try {
      await refreshSnapshot(runId);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="trace-debug-page">
      <Card
        title="Request / response trace"
        meta={
          <div className="card-actions">
            <button className="secondary" type="button" onClick={onExit}>
              Back
            </button>
            <button className="secondary" type="button" onClick={refresh} disabled={!runId || refreshing}>
              <RefreshCw size={14} />
              {refreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        }
      >
        <div className="trace-toolbar">
          <label className="field">
            <span>Discovery run</span>
            <select value={runId} onChange={(event) => void chooseRun(event.target.value)}>
              <option value="">Select a run</option>
              {discoveryRuns.map((run) => (
                <option value={run.id} key={run.id}>
                  {run.name || run.id} · {run.status}
                </option>
              ))}
            </select>
          </label>
          <div className="trace-run-summary">
            <span>Route</span>
            <strong>{runId ? `/trace?run=${runId}` : "/trace"}</strong>
          </div>
        </div>

        {!runId ? <p className="empty-copy">No discovery run selected.</p> : null}
        {runId && !latestRun ? (
          <p className="empty-copy">No agent trace has been recorded for this discovery run yet.</p>
        ) : null}

        {latestRun ? (
          <div className="trace-summary-grid">
            <TraceFact label="Run status" value={latestRun.status} tone={statusTone(latestRun.status)} />
            <TraceFact label="Phase" value={latestRun.current_phase || selectedRun?.stage || "-"} />
            <TraceFact label="Tool calls" value={String(latestRun.tool_call_count ?? toolCalls.length)} />
            <TraceFact label="LLM calls" value={String(latestRun.llm_call_count ?? countLlmCalls(toolCalls))} />
          </div>
        ) : null}
      </Card>

      {snapshot.sourceConfigs.length ? (
        <Card title="Source configuration">
          <div className="trace-stack">
            {snapshot.sourceConfigs.map((source) => (
              <article className="trace-call" key={source.id}>
                <header>
                  <div>
                    <strong>{source.provider_id}</strong>
                    <span>
                      {source.slot} · {source.mode} · priority {source.priority}
                    </span>
                  </div>
                  <StatusPill tone={source.enabled ? "green" : "gray"}>{source.enabled ? "enabled" : "disabled"}</StatusPill>
                </header>
                <div className="trace-request-response">
                  <JsonPanel label="Input" value={source.input} />
                  <JsonPanel label="Config" value={source.config} />
                </div>
              </article>
            ))}
          </div>
        </Card>
      ) : null}

      {steps.length ? (
        <Card title="Workflow steps">
          <div className="trace-step-list">
            {steps.map((step) => (
              <article className="trace-step" key={step.id}>
                <span>{step.sequence}</span>
                <div>
                  <strong>{step.phase}</strong>
                  <p>{step.objective}</p>
                  {step.error ? <em>{step.error}</em> : null}
                </div>
                <StatusPill tone={statusTone(step.status)}>{step.status}</StatusPill>
              </article>
            ))}
          </div>
        </Card>
      ) : null}

      {toolCalls.length ? (
        <Card title="Tool and LLM calls">
          <div className="trace-stack">
            {toolCalls.map((call) => (
              <TraceCallCard call={call} key={call.id} />
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  );
}

function TraceFact({ label, value, tone = "blue" }: { label: string; value: string; tone?: Tone }) {
  return (
    <div className="trace-fact">
      <span>{label}</span>
      <StatusPill tone={tone}>{value}</StatusPill>
    </div>
  );
}

function TraceCallCard({ call }: { call: ToolCall }) {
  return (
    <article className="trace-call">
      <header>
        <div>
          <strong>{call.tool_name}</strong>
          <span>{call.reason || "No reason recorded"}</span>
        </div>
        <StatusPill tone={statusTone(call.status)}>{call.status}</StatusPill>
      </header>
      {call.error ? <p className="trace-error">{call.error}</p> : null}
      <div className="trace-request-response">
        <JsonPanel label="Request" value={call.args} />
        <JsonPanel label="Response" value={call.observation ?? call.error ?? null} />
      </div>
    </article>
  );
}

function JsonPanel({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="trace-json-panel" open>
      <summary>{label}</summary>
      <pre>{formatJson(redact(value))}</pre>
    </details>
  );
}

function countLlmCalls(calls: ToolCall[]) {
  return calls.filter((call) => call.tool_name.startsWith("llm:")).length;
}

function formatJson(value: unknown) {
  if (value === undefined) return "undefined";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => redact(item));
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, entry]) => [
      key,
      shouldRedactKey(key) ? "[redacted]" : redact(entry),
    ]),
  );
}

function shouldRedactKey(key: string) {
  return /(api[_-]?key|authorization|bearer|password|secret|token)/i.test(key);
}
