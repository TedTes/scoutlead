import {
  CheckCircle2,
  CircleX,
  Copy,
  ExternalLink,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { StatusPill, useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { SourceItem } from "../types/domain";

type ReviewFilter = "needs_review" | "accepted" | "rejected" | "all";

export function SourceReviewScreen({
  onCountChange,
}: {
  onCountChange?: (runId: string, count: number) => void;
}) {
  const { selectedDiscoveryRun, selectedDiscoveryRunId, territoryApi } = useAppData();
  const { showToast } = useToast();
  const [items, setItems] = useState<SourceItem[]>([]);
  const [filter, setFilter] = useState<ReviewFilter>("needs_review");
  const [loading, setLoading] = useState(false);
  const [reviewingId, setReviewingId] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    if (!selectedDiscoveryRunId) return;
    setLoading(true);
    setError("");
    try {
      const loaded = await territoryApi.getDiscoveryRunSourceItems(selectedDiscoveryRunId);
      setItems(loaded);
      onCountChange?.(
        selectedDiscoveryRunId,
        loaded.filter((item) => item.state === "needs_review").length,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load source results.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // load is intentionally scoped to the selected immutable run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDiscoveryRunId]);

  const visibleItems = useMemo(
    () => items.filter((item) => matchesFilter(item, filter)),
    [filter, items],
  );

  const review = async (
    item: SourceItem,
    action: "accept" | "reject" | "duplicate" | "reaudit",
  ) => {
    if (!selectedDiscoveryRunId) return;
    setReviewingId(item.id);
    try {
      const updated = await territoryApi.reviewDiscoveryRunSourceItem(
        selectedDiscoveryRunId,
        item.id,
        action,
      );
      const next = items.map((entry) => entry.id === updated.id ? updated : entry);
      setItems(next);
      onCountChange?.(
        selectedDiscoveryRunId,
        next.filter((entry) => entry.state === "needs_review").length,
      );
      showToast({ title: reviewLabel(action), tone: "green" });
    } catch (cause) {
      showToast({
        title: "Review failed",
        message: cause instanceof Error ? cause.message : String(cause),
        tone: "red",
      });
    } finally {
      setReviewingId("");
    }
  };

  if (!selectedDiscoveryRunId) {
    return <div className="source-review-page"><p>Select a search to review its source results.</p></div>;
  }

  return (
    <section className="source-review-page">
      <header className="source-review-header">
        <div>
          <span>Source results</span>
          <h1>Review queue</h1>
          <p>{selectedDiscoveryRun?.name || "Selected search"}</p>
        </div>
        <button className="secondary" disabled={loading} onClick={() => void load()} type="button">
          <RefreshCw className={loading ? "is-spinning" : ""} size={15} />
          Refresh
        </button>
      </header>

      <div className="source-review-tabs" role="tablist" aria-label="Source review filter">
        {(["needs_review", "accepted", "rejected", "all"] as const).map((value) => (
          <button
            className={filter === value ? "active" : ""}
            key={value}
            onClick={() => setFilter(value)}
            role="tab"
            type="button"
          >
            {filterLabel(value)} <span>{items.filter((item) => matchesFilter(item, value)).length}</span>
          </button>
        ))}
      </div>

      {error ? <p className="source-review-error">{error}</p> : null}
      {!loading && !visibleItems.length ? <p className="source-review-empty">No source results in this state.</p> : null}
      <div className="source-review-list">
        {visibleItems.map((item) => (
          <article className="source-review-row" key={item.id}>
            <div className="source-review-main">
              <strong>{item.title || "Untitled source result"}</strong>
              <span>{item.provider_id} · {item.query}</span>
              <small>{item.decisions[item.decisions.length - 1]?.reason || "Awaiting judgment."}</small>
              {item.source_url ? (
                <a href={item.source_url} rel="noreferrer" target="_blank">
                  Open source <ExternalLink size={12} />
                </a>
              ) : null}
            </div>
            <StatusPill tone={itemTone(item.state)}>{item.state.replace(/_/g, " ")}</StatusPill>
            <div className="source-review-actions">
              <button aria-label="Accept" className="icon-button" disabled={reviewingId === item.id} onClick={() => void review(item, "accept")} title="Accept" type="button"><CheckCircle2 size={15} /></button>
              <button aria-label="Reject" className="icon-button" disabled={reviewingId === item.id} onClick={() => void review(item, "reject")} title="Reject" type="button"><CircleX size={15} /></button>
              <button aria-label="Mark duplicate" className="icon-button" disabled={reviewingId === item.id} onClick={() => void review(item, "duplicate")} title="Mark duplicate" type="button"><Copy size={15} /></button>
              <button aria-label="Re-audit" className="icon-button" disabled={reviewingId === item.id || !item.business_id} onClick={() => void review(item, "reaudit")} title="Re-audit" type="button"><RotateCcw size={15} /></button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function matchesFilter(item: SourceItem, filter: ReviewFilter): boolean {
  if (filter === "all") return true;
  if (filter === "needs_review") return item.state === "needs_review";
  if (filter === "rejected") return ["rejected", "excluded", "failed"].includes(item.state);
  return ["relevant", "identity_resolved", "audit_pending", "audited", "eligible"].includes(item.state);
}

function filterLabel(filter: ReviewFilter): string {
  if (filter === "needs_review") return "Needs review";
  return filter[0].toUpperCase() + filter.slice(1);
}

function reviewLabel(action: "accept" | "reject" | "duplicate" | "reaudit"): string {
  return {
    accept: "Source accepted",
    reject: "Source rejected",
    duplicate: "Duplicate recorded",
    reaudit: "Re-audit queued",
  }[action];
}

function itemTone(state: SourceItem["state"]): "green" | "amber" | "red" | "gray" {
  if (["rejected", "excluded", "failed"].includes(state)) return "red";
  if (state === "needs_review") return "amber";
  if (["relevant", "identity_resolved", "audit_pending", "audited", "eligible"].includes(state)) return "green";
  return "gray";
}
