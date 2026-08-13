import { Plus } from "lucide-react";
import { useAppData } from "../state/app-data";
import { Card, LimitRow, PageHeader, StatusPill } from "../shared-ui";
import type { ConnectionStatus } from "../types/domain";

export function ConnectionsScreen() {
  const { connections } = useAppData();

  return (
    <>
      <PageHeader
        title="Connections"
        subtitle="Integrations powering discovery, enrichment, and sending."
        actions={
          <button>
            <Plus size={14} />
            Add integration
          </button>
        }
      />

      <div className="integration-grid">
        {connections.length === 0 ? (
          <article className="integration-card">
            <div>
              <strong>No connection status available</strong>
              <p>Backend `/connections/status` is not reachable yet.</p>
            </div>
          </article>
        ) : (
          connections.map((connection) => (
            <ConnectionCard connection={connection} key={`${connection.category}-${connection.name}`} />
          ))
        )}
      </div>

      <Card title="Sending limits & health" meta={<StatusPill tone="green">Runtime visible</StatusPill>}>
        <div className="limits">
          <LimitRow label="Database" value={statusLabel(connections, "persistence")} width={100} tone="green" />
          <LimitRow label="Reasoning" value={statusLabel(connections, "reasoning")} width={70} tone="blue" />
          <LimitRow label="Outreach" value={statusLabel(connections, "outreach")} width={40} tone="amber" />
        </div>
      </Card>
    </>
  );
}

function ConnectionCard({ connection }: { connection: ConnectionStatus }) {
  const tone = connection.status === "connected" ? "green" : connection.status === "degraded" ? "amber" : "gray";
  return (
    <article className="integration-card">
      <span className={`integration-logo tone-${tone}`}>{connection.name.slice(0, 2).toUpperCase()}</span>
      <div>
        <strong>{connection.name}</strong>
        <p>{connection.detail}</p>
      </div>
      <div className="integration-side">
        <StatusPill tone={tone}>{connection.status}</StatusPill>
        <span>{connection.category}</span>
      </div>
    </article>
  );
}

function statusLabel(connections: ConnectionStatus[], category: string) {
  return connections.find((connection) => connection.category === category)?.status || "unknown";
}
