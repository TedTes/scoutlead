import { Card, StatusPill } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { AgentRunDetail, AgentStep, CampaignSource, DiscoveryCandidate, ToolCall } from "../types/domain";
import { statusTone } from "../utils/status";

export function TraceScreen() {
  const { selectedCampaign, snapshot } = useAppData();
  const trace = snapshot.trace;
  const latestRun = trace?.latest_run ?? snapshot.latestAgentRun;

  if (!selectedCampaign) {
    return (
      <Card title="Trace">
        <p className="empty-copy">Select a campaign to inspect its run trace.</p>
      </Card>
    );
  }

  if (!latestRun) {
    return (
      <Card title="Trace">
        <p className="empty-copy">No run trace exists yet. Run this campaign to record step, tool, and LLM inputs and outputs.</p>
      </Card>
    );
  }

  return (
    <div className="trace-page">
      <CampaignSourceTrace sources={snapshot.campaignSources} />
      <CandidateTrace candidates={snapshot.discoveryCandidates} />

      <Card
        title="Run trace"
        meta={
          <div className="card-actions">
            <StatusPill tone={statusTone(latestRun.status)}>{latestRun.status}</StatusPill>
            <span className="muted-count">{trace?.run_count ?? 1} runs</span>
          </div>
        }
      >
        <div className="trace-run-summary">
          <TraceMetric label="Run" value={shortId(latestRun.id)} />
          <TraceMetric label="Phase" value={latestRun.current_phase || "complete"} />
          <TraceMetric label="Tools" value={String(latestRun.tool_call_count)} />
          <TraceMetric label="LLM" value={String(latestRun.llm_call_count)} />
          <TraceMetric label="Started" value={formatTimestamp(latestRun.started_at || latestRun.created_at)} />
        </div>
        <p className="trace-objective">{latestRun.objective}</p>
        {latestRun.error ? <p className="form-error">{latestRun.error}</p> : null}
      </Card>

      <TraceSteps run={latestRun} />

      {trace && trace.runs.length > 1 ? (
        <Card title="Previous runs">
          <div className="trace-run-list">
            {trace.runs.slice(1).map((run) => (
              <div className="trace-run-row" key={run.id}>
                <strong>{shortId(run.id)}</strong>
                <StatusPill tone={statusTone(run.status)}>{run.status}</StatusPill>
                <span>{formatTimestamp(run.created_at)}</span>
                <span>{run.tool_call_count} tools</span>
                <span>{run.llm_call_count} LLM</span>
              </div>
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  );
}

function CampaignSourceTrace({ sources }: { sources: CampaignSource[] }) {
  if (!sources.length) return null;

  return (
    <Card title="Campaign sources" meta={<span className="muted-count">{sources.length} configured</span>}>
      <div className="trace-candidate-list">
        {sources.map((source) => (
          <details className="trace-call" key={source.id}>
            <summary>
              <div>
                <strong>{source.provider_id}</strong>
                <span>{source.slot} / {source.mode}</span>
                <span>{getSourceQuery(source)}</span>
              </div>
              <StatusPill tone={source.enabled ? "green" : "gray"}>
                {source.enabled ? "enabled" : "disabled"}
              </StatusPill>
            </summary>
            <div className="trace-call-body">
              <TraceJson title="Input" value={source.input} />
              <TraceJson title="Config" value={source.config} />
            </div>
          </details>
        ))}
      </div>
    </Card>
  );
}

function CandidateTrace({ candidates }: { candidates: DiscoveryCandidate[] }) {
  if (!candidates.length) return null;

  const promoted = candidates.filter((candidate) => candidate.lead_id);
  const rejected = candidates.filter((candidate) => candidate.rejection_reason);
  const byType = candidates.reduce<Record<string, number>>((counts, candidate) => {
    counts[candidate.candidate_type] = (counts[candidate.candidate_type] ?? 0) + 1;
    return counts;
  }, {});

  return (
    <Card
      title="Discovery candidates"
      meta={
        <div className="card-actions">
          <span className="muted-count">{promoted.length} promoted</span>
          <span className="muted-count">{rejected.length} rejected</span>
        </div>
      }
    >
      <div className="trace-candidate-summary">
        {Object.entries(byType).map(([type, count]) => (
          <span key={type}>
            {type}: <strong>{count}</strong>
          </span>
        ))}
      </div>
      <div className="trace-candidate-list">
        {candidates.slice(0, 12).map((candidate) => (
          <details className="trace-call" key={candidate.id}>
            <summary>
              <div>
                <strong>{candidate.title}</strong>
                <span>{candidate.query}</span>
                {candidate.rejection_reason ? <span>{candidate.rejection_reason}</span> : null}
              </div>
              <StatusPill tone={candidate.lead_id ? "green" : candidate.rejection_reason ? "gray" : "amber"}>
                {candidate.lead_id ? "promoted" : candidate.candidate_type}
              </StatusPill>
            </summary>
            <div className="trace-call-body">
              <div className="trace-meta-row">
                <span>{candidate.url || "-"}</span>
                <span>{candidate.confidence}% confidence</span>
              </div>
              <TraceJson title="Raw candidate" value={candidate.raw} />
            </div>
          </details>
        ))}
      </div>
    </Card>
  );
}

function TraceSteps({ run }: { run: AgentRunDetail }) {
  const callsByStep = groupCallsByStep(run.tool_calls);
  const orphanCalls = callsByStep.get("__run__") ?? [];

  return (
    <div className="trace-step-list">
      {run.steps.map((step) => (
        <TraceStep key={step.id} step={step} calls={callsByStep.get(step.id) ?? []} />
      ))}
      {orphanCalls.length ? (
        <Card title="Run-level calls">
          <div className="trace-call-list">
            {orphanCalls.map((call) => (
              <TraceCall key={call.id} call={call} />
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  );
}

function TraceStep({ step, calls }: { step: AgentStep; calls: ToolCall[] }) {
  return (
    <Card
      title={`${step.sequence}. ${step.phase}`}
      meta={
        <div className="card-actions">
          <StatusPill tone={statusTone(step.status)}>{step.status}</StatusPill>
          <span className="muted-count">{calls.length} calls</span>
        </div>
      }
    >
      <p className="trace-objective">{step.objective}</p>
      {step.error ? <p className="form-error">{step.error}</p> : null}

      <div className="trace-io-grid">
        <TraceJson title="Step input" value={step.input_snapshot} />
        <TraceJson title="Step output" value={step.output_snapshot ?? step.observation ?? {}} />
      </div>

      {calls.length ? (
        <div className="trace-call-list">
          {calls.map((call) => (
            <TraceCall key={call.id} call={call} />
          ))}
        </div>
      ) : null}
    </Card>
  );
}

function TraceCall({ call }: { call: ToolCall }) {
  const failed = call.status === "failed";
  const query = getCallQuery(call.args);
  return (
    <details className="trace-call">
      <summary>
        <div>
          <strong>{call.tool_name}</strong>
          {call.reason ? <span>{call.reason}</span> : null}
          {query ? <span>Query: {query}</span> : null}
        </div>
        <StatusPill tone={statusTone(call.status)}>{call.status}</StatusPill>
      </summary>
      <div className="trace-call-body">
        <div className="trace-meta-row">
          <span>{shortId(call.id)}</span>
          <span>{formatTimestamp(call.started_at || call.created_at)}</span>
        </div>
        <div className="trace-io-grid">
          <TraceJson title="Input" value={call.args} />
          <TraceJson title={failed ? "Error" : "Output"} value={failed ? call.error : call.observation} />
        </div>
      </div>
    </details>
  );
}

function getCallQuery(args: Record<string, unknown>) {
  const resolvedQuery = args.resolved_query;
  if (typeof resolvedQuery === "string" && resolvedQuery.trim()) return resolvedQuery.trim();

  const query = args.query;
  if (typeof query === "string" && query.trim()) return query.trim();

  const source = args.source;
  if (source && typeof source === "object" && "input" in source) {
    const input = (source as { input?: Record<string, unknown> }).input;
    const value = input?.query;
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  if (source && typeof source === "object" && "value" in source) {
    const value = (source as { value?: unknown }).value;
    if (typeof value === "string" && value.trim()) return value.trim();
  }

  return "";
}

function getSourceQuery(source: CampaignSource) {
  const query = source.input.query;
  return typeof query === "string" ? query : "";
}

function TraceJson({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="trace-json" open>
      <summary>{title}</summary>
      <pre>{formatJson(value)}</pre>
    </details>
  );
}

function TraceMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function groupCallsByStep(calls: ToolCall[]) {
  const grouped = new Map<string, ToolCall[]>();
  for (const call of calls) {
    const key = call.step_id || "__run__";
    grouped.set(key, [...(grouped.get(key) ?? []), call]);
  }
  return grouped;
}

function formatJson(value: unknown) {
  if (value === undefined || value === null || value === "") return "null";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function shortId(value: string) {
  return value.length > 16 ? `${value.slice(0, 16)}...` : value;
}

function formatTimestamp(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
