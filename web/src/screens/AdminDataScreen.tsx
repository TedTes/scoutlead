import {
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Copy,
  Download,
  ExternalLink,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { ApiClient } from "../api/client";
import type {
  AdminAttributeDefinition,
  AdminBusinessDetail,
  AdminBusinessSummary,
  AdminFactLineageFact,
  AdminFactLineage,
  AdminOverview,
} from "../types/domain";
import "./AdminDataScreen.css";

const emptyOverview: AdminOverview = {
  total: 0,
  active: 0,
  quarantined: 0,
  archived: 0,
  fully_validated: 0,
  needs_attention: 0,
  incomplete: 0,
  searchable: 0,
  trade_groups: [],
};

export function AdminDataScreen({ api }: { api: ApiClient }) {
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [overview, setOverview] = useState(emptyOverview);
  const [rows, setRows] = useState<AdminBusinessSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [quality, setQuality] = useState("");
  const [sort, setSort] = useState("score_asc");
  const [status, setStatus] = useState("");
  const [nicheSlug, setNicheSlug] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [selectedBusinesses, setSelectedBusinesses] = useState<Record<string, AdminBusinessSummary>>({});
  const [detail, setDetail] = useState<AdminBusinessDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState<"add" | "edit" | "delete" | null>(null);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      await api.getAdminAccess();
      setAllowed(true);
      const summary = await api.getAdminOverview();
      const tradeGroups = summary.trade_groups || [];
      const selectedNiche = tradeGroups.some((group) => group.slug === nicheSlug)
        ? nicheSlug
        : tradeGroups[0]?.slug || "";
      if (selectedNiche !== nicheSlug) setNicheSlug(selectedNiche);
      const businessPage = await api.getAdminBusinesses({
        q: search,
        quality,
        sort,
        status,
        niche_slug: selectedNiche,
        page,
        page_size: 50,
      });
      setOverview(summary);
      setRows(businessPage.items);
      setSelectedBusinesses((current) => {
        const next = { ...current };
        businessPage.items.forEach((row) => {
          if (next[row.id]) next[row.id] = row;
        });
        return next;
      });
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
  }, [api, nicheSlug, page, quality, search, sort, status]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 180);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (!selectedId || !allowed) {
      setDetail(null);
      return;
    }
    void api.getAdminBusiness(selectedId).then(setDetail).catch((cause) => {
      setError(cause instanceof Error ? cause.message : String(cause));
    });
  }, [allowed, api, selectedId]);

  const refreshDetail = async (result?: AdminBusinessDetail) => {
    if (result) {
      setDetail(result);
      setSelectedId(result.id);
    }
    await load();
  };
  const selectedCount = Object.keys(selectedBusinesses).length;
  const allVisibleSelected = rows.length > 0 && rows.every((row) => selectedBusinesses[row.id]);
  const someVisibleSelected = rows.some((row) => selectedBusinesses[row.id]);
  const toggleVisibleSelection = () => {
    setSelectedBusinesses((current) => {
      const next = { ...current };
      if (allVisibleSelected) rows.forEach((row) => delete next[row.id]);
      else rows.forEach((row) => { next[row.id] = row; });
      return next;
    });
  };
  const toggleBusinessSelection = (row: AdminBusinessSummary) => {
    setSelectedBusinesses((current) => {
      const next = { ...current };
      if (next[row.id]) delete next[row.id];
      else next[row.id] = row;
      return next;
    });
  };
  const exportSelectedJson = async () => {
    if (!selectedCount) return;
    setExporting(true);
    setError("");
    try {
      const businessIds = Object.keys(selectedBusinesses);
      const businesses: unknown[] = [];
      for (let index = 0; index < businessIds.length; index += 5) {
        const batch = businessIds.slice(index, index + 5);
        const batchPayloads = await Promise.all(batch.map(async (businessId) => {
          const [businessDetail, businessLineage] = await Promise.all([
            api.getAdminBusiness(businessId),
            api.getAdminBusinessFactLineage(businessId),
          ]);
          return buildBusinessJsonPayload(businessDetail, businessLineage);
        }));
        businesses.push(...batchPayloads);
      }
      const payload = {
        exported_at: new Date().toISOString(),
        business_count: businesses.length,
        businesses,
      };
      downloadJson(payload, `scoutlead-businesses-${new Date().toISOString().slice(0, 10)}.json`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setExporting(false);
    }
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

  const pageHeader = typeof document !== "undefined"
    ? document.getElementById("admin-page-header")
    : null;

  return (
    <section className="admin-data-screen admin-business-data-screen">
      {pageHeader ? createPortal(<div className="admin-business-header">
        <div className="admin-metrics admin-business-metrics" aria-label="Business quality overview">
          <Metric label="Businesses" value={overview.total} />
          <Metric label="Validated" value={overview.fully_validated} tone="good" />
          <Metric label="Needs attention" value={overview.needs_attention} tone="warn" />
          <Metric label="Incomplete" value={overview.incomplete} />
          <Metric label="Searchable" value={overview.searchable} />
        </div>
        <button className="admin-primary-button" type="button" onClick={() => setDialog("add")}>
          <Plus size={15} /> Add business
        </button>
      </div>, pageHeader) : null}

      {overview.trade_groups.length ? (
        <nav className="admin-trade-chips" aria-label="Business trades">
          {overview.trade_groups.map((group) => (
            <button
              aria-pressed={group.slug === nicheSlug}
              className={group.slug === nicheSlug ? "active" : ""}
              key={group.slug}
              type="button"
              onClick={() => {
                setNicheSlug(group.slug);
                setPage(1);
                setSelectedId("");
              }}
            >
              <span>{group.label}</span>
              <strong>{group.count.toLocaleString()}</strong>
            </button>
          ))}
        </nav>
      ) : null}

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
        <select aria-label="Record quality" value={quality} onChange={(event) => { setQuality(event.target.value); setPage(1); }}>
          <option value="">All quality</option>
          <option value="pending">Pending validation</option>
          <option value="poor">Poor · 0–64</option>
          <option value="review">Review · 65–84</option>
          <option value="reliable">Reliable · 85–100</option>
        </select>
        <select aria-label="Business state" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
          <option value="">All states</option>
          <option value="active">Active</option>
          <option value="quarantined">Quarantined</option>
          <option value="archived">Archived</option>
        </select>
        <select aria-label="Sort businesses" value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}>
          <option value="score_asc">Lowest record quality first</option>
          <option value="score_desc">Highest record quality first</option>
          <option value="name">Name A–Z</option>
        </select>
        <button
          className="admin-export-button"
          disabled={!selectedCount || exporting}
          type="button"
          onClick={() => void exportSelectedJson()}
        >
          <Download size={14} /> {exporting ? "Preparing…" : `Export JSON ${selectedCount || ""}`}
        </button>
        <button className="admin-icon-button" title="Refresh" type="button" onClick={() => void load()}>
          <RefreshCw size={15} />
        </button>
      </div>

      {error ? <div className="admin-error"><CircleAlert size={15} /> {error}</div> : null}

      <div className="admin-workspace admin-leads-workspace">
        <div className="admin-table-pane">
          <table className="admin-business-table">
            <thead><tr>
              <th className="admin-select-column"><input
                aria-checked={someVisibleSelected && !allVisibleSelected ? "mixed" : allVisibleSelected}
                aria-label="Select businesses on this page"
                checked={allVisibleSelected}
                ref={(input) => { if (input) input.indeterminate = someVisibleSelected && !allVisibleSelected; }}
                type="checkbox"
                onChange={toggleVisibleSelection}
              /></th>
              <th>Business</th><th>Market</th><th>Record quality</th><th>State</th>
            </tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr className={`${row.id === selectedId ? "is-selected" : ""} ${selectedBusinesses[row.id] ? "is-checked" : ""}`} key={row.id} onClick={() => setSelectedId(row.id)}>
                  <td className="admin-select-column"><input aria-label={`Select ${row.display_name}`} checked={Boolean(selectedBusinesses[row.id])} type="checkbox" onClick={(event) => event.stopPropagation()} onChange={() => toggleBusinessSelection(row)} /></td>
                  <td><strong>{row.display_name}</strong><span>{row.niche_label || "Unclassified"}</span></td>
                  <td><strong>{row.market_key || "Unknown"}</strong><span>{row.address || row.geography || "No address"}</span></td>
                  <td><QualityScore row={row} /></td>
                  <td><StatusPill value={row.status} /></td>
                </tr>
              ))}
              {!loading && !rows.length ? <tr><td colSpan={5} className="admin-empty">No businesses match these filters.</td></tr> : null}
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

        <BusinessInspector api={api} detail={detail} />
      </div>

      {dialog === "add" ? <BusinessForm api={api} mode="add" onClose={() => setDialog(null)} onSaved={(value) => { setDialog(null); void refreshDetail(value); }} /> : null}
      {dialog === "edit" && detail ? <BusinessForm api={api} mode="edit" detail={detail} onClose={() => setDialog(null)} onSaved={(value) => { setDialog(null); void refreshDetail(value); }} /> : null}
      {dialog === "delete" && detail ? <DeleteDialog api={api} detail={detail} onClose={() => setDialog(null)} onDeleted={() => { setDialog(null); setSelectedId(""); void load(); }} /> : null}
    </section>
  );
}

function Metric({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return <div className={`admin-metric ${tone}`}><span>{label}:</span><strong>{value.toLocaleString()}</strong></div>;
}

function StatusPill({ value }: { value: string }) {
  return <span className={`admin-status-pill is-${value.replace(/_/g, "-")}`}>{value.replace(/_/g, " ")}</span>;
}

function QualityScore({ row }: { row: AdminBusinessSummary }) {
  const breakdown = row.data_quality_breakdown;
  const validationScores = breakdown.validation_scores || [];
  const title = [
    validationScores.length
      ? "Required business-record validations"
      : "Validation details are not available from the running API",
    ...validationScores.map((validation) => `${validation.label}: ${validation.status} (${validation.score})`),
    ...(breakdown.limitations || []),
  ].join(" · ");
  return (
    <span className={`admin-quality-score is-${row.data_quality_label}`} title={title}>
      <strong>{row.data_quality_score ?? "—"}</strong>
      <small>{row.data_quality_label}</small>
    </span>
  );
}

function downloadJson(payload: unknown, filename: string) {
  const json = JSON.stringify(payload, null, 2);
  const url = URL.createObjectURL(new Blob([json], { type: "application/json;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function BusinessInspector({
  api,
  detail,
}: {
  api: ApiClient;
  detail: AdminBusinessDetail | null;
}) {
  const [lineage, setLineage] = useState<AdminFactLineage | null>(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [lineageError, setLineageError] = useState("");
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<"attributes" | "json">("attributes");
  const loadLineage = useCallback(async () => {
    if (!detail?.id) {
      setLineage(null);
      return;
    }
    setLineageLoading(true);
    setLineageError("");
    try {
      setLineage(await api.getAdminBusinessFactLineage(detail.id));
    } catch (cause) {
      setLineageError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLineageLoading(false);
    }
  }, [api, detail?.id]);
  useEffect(() => {
    void loadLineage();
  }, [loadLineage]);
  useEffect(() => {
    setActiveTab("attributes");
    setCopied(false);
  }, [detail?.id]);
  const jsonPayload = useMemo(
    () => detail && lineage ? buildBusinessJsonPayload(detail, lineage) : null,
    [detail, lineage],
  );
  const copyJson = async () => {
    if (!jsonPayload) return;
    await navigator.clipboard.writeText(JSON.stringify(jsonPayload, null, 2));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  if (!detail) return <aside className="admin-inspector is-empty">Select a business to view its attributes.</aside>;

  return (
    <aside className="admin-inspector">
      <header>
        <div><h2>{detail.display_name}</h2><p>Business attributes and evidence</p></div>
        <div className="admin-json-actions">
          <AttributeCoverage lineage={lineage} />
        </div>
      </header>
      <nav className="admin-inspector-tabs" aria-label="Business detail views">
        <button className={activeTab === "attributes" ? "is-active" : ""} type="button" onClick={() => setActiveTab("attributes")}>Attributes</button>
        <button className={activeTab === "json" ? "is-active" : ""} type="button" onClick={() => setActiveTab("json")}>JSON</button>
        {activeTab === "json" ? <button className="admin-json-copy" disabled={!jsonPayload} type="button" onClick={() => void copyJson()}>
          <Copy size={12} /> {copied ? "Copied" : "Copy JSON"}
        </button> : null}
      </nav>
      {activeTab === "attributes" ? (
        <BusinessAttributeRecord detail={detail} error={lineageError} lineage={lineage} loading={lineageLoading} />
      ) : (
        <div className="admin-inspector-content admin-json-inspector">
          {lineageLoading && !jsonPayload ? <p className="admin-record-empty">Preparing JSON…</p> : null}
          {lineageError && !jsonPayload ? <p className="admin-record-empty">Business JSON is unavailable.</p> : null}
          {jsonPayload ? <pre>{JSON.stringify(jsonPayload, null, 2)}</pre> : null}
        </div>
      )}
    </aside>
  );
}

function buildBusinessJsonPayload(detail: AdminBusinessDetail, lineage: AdminFactLineage) {
  const factsByKey = new Map(lineage.facts.map((fact) => [fact.key, fact]));
  const observationsById = new Map(lineage.observations.map((observation) => [observation.id, observation]));
  const definitions = lineage.attribute_definitions.length
    ? lineage.attribute_definitions
    : FALLBACK_ATTRIBUTE_DEFINITIONS;
  const fallbackValues: Record<string, unknown> = {
    business_name: detail.display_name,
    trade_category: detail.niche_label || detail.niche_slug,
    address: detail.address,
    phone: detail.phone,
    website_url: detail.website_url,
    domain: detail.domain,
    latitude: detail.latitude,
    longitude: detail.longitude,
    is_directory: detail.is_directory,
    is_chain: detail.is_chain,
    is_franchise: detail.is_franchise,
  };
  const attributes = Object.fromEntries(definitions.map((definition) => {
    const fact = factsByKey.get(definition.key);
    const value = fact?.value ?? fallbackValues[definition.key] ?? null;
    const observation = fact?.source_observation_id
      ? observationsById.get(fact.source_observation_id)
      : undefined;
    return [definition.key, {
      label: definition.label,
      category: definition.category,
      observed: value !== null && value !== "",
      value,
      footprint_score: fact?.attribute_score ?? null,
      score_reason: fact?.score_reason ?? null,
      evidence_confidence: fact?.evidence_confidence ?? null,
      resolution_state: fact?.resolution_state ?? null,
      quality_state: fact?.quality_state ?? null,
      observed_at: fact?.observed_at ?? null,
      expires_at: fact?.expires_at ?? null,
      source: observation ? {
        observation_id: observation.id,
        provider: observation.source,
        url: observation.source_url,
      } : null,
    }];
  }));
  return {
    business: {
      id: detail.id,
      name: detail.display_name,
      state: detail.status,
      trade: detail.niche_label,
      market: detail.market_key,
      address: detail.address,
      coordinates: { latitude: detail.latitude, longitude: detail.longitude },
      website_url: detail.website_url,
      domain: detail.domain,
      phone: detail.phone,
      first_seen_at: detail.first_seen_at,
      last_seen_at: detail.last_seen_at,
    },
    record_quality: {
      score: detail.data_quality_score,
      label: detail.data_quality_label,
      required_checks: detail.data_quality_breakdown.validation_scores,
      limitations: detail.data_quality_breakdown.limitations,
    },
    attributes,
    contacts: detail.contacts,
    evidence: {
      facts: lineage.facts,
      claims: lineage.claims,
      observations: lineage.observations,
    },
  };
}

function BusinessAttributeRecord({
  detail,
  lineage,
  loading,
  error,
}: {
  detail: AdminBusinessDetail;
  lineage: AdminFactLineage | null;
  loading: boolean;
  error: string;
}) {
  if (loading && !lineage) return <div className="admin-inspector-content"><p className="admin-record-empty">Loading attributes…</p></div>;
  if (error && !lineage) return <div className="admin-inspector-content"><p className="admin-record-empty">Business attributes are unavailable.</p></div>;

  const definitions = lineage?.attribute_definitions?.length
    ? lineage.attribute_definitions
    : FALLBACK_ATTRIBUTE_DEFINITIONS;
  const factsByKey = new Map((lineage?.facts || []).map((fact) => [fact.key, fact]));
  const observationsById = new Map((lineage?.observations || []).map((observation) => [observation.id, observation]));
  const fallbackValues: Record<string, unknown> = {
    business_name: detail.display_name,
    trade_category: detail.niche_label || detail.niche_slug,
    address: detail.address,
    phone: detail.phone,
    website_url: detail.website_url,
    domain: detail.domain,
    latitude: detail.latitude,
    longitude: detail.longitude,
    is_directory: detail.is_directory,
    is_chain: detail.is_chain,
    is_franchise: detail.is_franchise,
  };
  const groups = [...new Map(
    [...definitions]
      .sort((a, b) => a.category_sort_order - b.category_sort_order || a.sort_order - b.sort_order)
      .map((definition) => [definition.category, {
        key: definition.category,
        label: definition.category_label,
        definitions: definitions.filter((item) => item.category === definition.category),
      }])
  ).values()];

  return (
    <div className="admin-inspector-content admin-business-record">
      {groups.map((group) => <AttributeSection title={group.label} key={group.key}>
        {group.definitions.map((definition) => {
          const fact = factsByKey.get(definition.key);
          const fallbackValue = fallbackValues[definition.key];
          const observation = fact?.source_observation_id
            ? observationsById.get(fact.source_observation_id)
            : undefined;
          return <TrackedAttributeRow
            definition={definition}
            fact={fact}
            fallbackValue={fallbackValue}
            key={definition.key}
            source={observation?.source}
          />;
        })}
      </AttributeSection>)}
    </div>
  );
}

function AttributeSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="admin-attribute-section"><h3>{title}</h3>{children}</section>;
}

function AttributeCoverage({ lineage }: { lineage: AdminFactLineage | null }) {
  const definitions = lineage?.attribute_definitions?.length
    ? lineage.attribute_definitions
    : FALLBACK_ATTRIBUTE_DEFINITIONS;
  const trackedKeys = new Set(definitions.map((definition) => definition.key));
  const total = definitions.length;
  const observed = lineage?.facts.filter((fact) => trackedKeys.has(fact.key) && fact.value != null).length || 0;
  return <span className="admin-attribute-coverage"><strong>{observed}</strong> / {total} observed</span>;
}

function TrackedAttributeRow({
  definition,
  fact,
  fallbackValue,
  source,
}: {
  definition: AdminAttributeDefinition;
  fact?: AdminFactLineageFact;
  fallbackValue?: unknown;
  source?: string;
}) {
  const value = fact?.value ?? fallbackValue;
  const observed = value !== null && value !== undefined && value !== "";
  const confidence = fact?.evidence_confidence ?? fact?.confidence;
  return <article className={`admin-business-attribute tracked-attribute${observed ? "" : " is-unobserved"}`}>
    <div>
      <span><strong>{definition.label}</strong><code>{definition.key}</code></span>
      <FootprintScore score={fact?.attribute_score} reason={fact?.score_reason} />
    </div>
    <p>{observed ? formatAttributeValue(definition.key, value) : "Not observed"}</p>
    <small>
      {fact
        ? <>{confidence != null ? `Evidence ${confidence}%` : "Confidence unavailable"} · {humanizeKey(fact.quality_state)}{source ? ` · ${humanizeKey(source)}` : ""}</>
        : definition.status === "not_configured" ? "Attribute is not configured in this deployment" : "No observation collected"}
    </small>
  </article>;
}

function FootprintScore({ score, reason }: { score?: number | null; reason?: string | null }) {
  if (score == null) return <span className="admin-footprint-score is-unscored">— <small>unscored</small></span>;
  const state = score >= 85 ? "strong" : score >= 65 ? "fair" : score >= 40 ? "weak" : "gap";
  return <span className={`admin-footprint-score is-${state}`} title={reason || undefined}><strong>{score}</strong><small>{state}</small></span>;
}

function formatAttributeValue(key: string, value: unknown) {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  const rendered = String(value);
  if ((key.endsWith("_url") || key === "website_url") && /^https?:\/\//i.test(rendered)) {
    return <a href={rendered} target="_blank" rel="noreferrer">{rendered}<ExternalLink size={11} /></a>;
  }
  return rendered;
}

function humanizeKey(value: string) {
  return value.replace(/_/g, " ");
}

const FALLBACK_ATTRIBUTE_GROUPS: Array<[string, string, string[]]> = [
  ["identity", "Core identity and targeting", ["business_name", "business_operational", "trade_category", "provider_business_id", "address", "city", "region", "postal_code", "latitude", "longitude", "phone", "website_url", "domain", "is_directory", "is_chain", "is_franchise"]],
  ["website", "Website opportunity", ["website_status", "website_ownership", "http_status", "uses_https", "mobile_viewport_present", "website_quality_score", "performance_score", "accessibility_score", "best_practices_score"]],
  ["lead_capture", "Lead-capture opportunity", ["contact_form_present", "contact_page_url", "quote_or_booking_form_present", "booking_url", "primary_cta_present", "click_to_call_present", "public_email_present", "public_phone_present"]],
  ["reputation", "Reputation opportunity", ["google_rating", "google_review_count", "review_recency_days"]],
  ["local_visibility", "Local visibility", ["google_business_profile_present", "local_business_schema_present", "service_area_content_present", "title_and_meta_present"]],
  ["outreach", "Outreach readiness", ["verified_email", "verified_phone", "contact_form_url", "preferred_contact_channel"]],
];

const FALLBACK_ATTRIBUTE_DEFINITIONS: AdminAttributeDefinition[] = FALLBACK_ATTRIBUTE_GROUPS.flatMap(
  ([category, categoryLabel, keys], categorySortOrder) => keys.map((key, sortOrder) => ({
    key,
    label: key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()),
    category,
    category_label: categoryLabel,
    category_sort_order: categorySortOrder,
    sort_order: sortOrder,
    value_type: "text",
    status: "not_configured",
  }))
);

function BusinessForm({ api, mode, detail, onClose, onSaved }: { api: ApiClient; mode: "add" | "edit"; detail?: AdminBusinessDetail; onClose: () => void; onSaved: (value: AdminBusinessDetail) => void }) {
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
      const result = mode === "add" ? await api.createAdminBusiness(payload) : await api.updateAdminBusiness(detail!.id, payload);
      onSaved(result);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setSaving(false); }
  };
  return <div className="admin-dialog-backdrop" role="presentation"><div className="admin-dialog" role="dialog" aria-modal="true"><header><div><h2>{mode === "add" ? "Add business" : "Edit business"}</h2><p>{mode === "add" ? "New records start quarantined until reviewed." : "Canonical changes quarantine the record and are written to audit history."}</p></div><button className="admin-icon-button" title="Close" type="button" onClick={onClose}><X size={16} /></button></header><div className="admin-form-grid"><Field label="Business name" value={form.display_name} onChange={(value) => set("display_name", value)} />{mode === "add" ? <><Field label="Niche slug" value={form.niche_slug} onChange={(value) => set("niche_slug", value)} /><Field label="Market key" value={form.market_key} onChange={(value) => set("market_key", value)} /></> : null}<Field label="Address" value={form.address} onChange={(value) => set("address", value)} /><Field label="Geography" value={form.geography} onChange={(value) => set("geography", value)} /><Field label="Phone" value={form.phone} onChange={(value) => set("phone", value)} /><Field label="Website" value={form.website_url} onChange={(value) => set("website_url", value)} /><Field label="Latitude" value={form.latitude} onChange={(value) => set("latitude", value)} /><Field label="Longitude" value={form.longitude} onChange={(value) => set("longitude", value)} />{mode === "add" ? <><Field label="Evidence URL" value={form.source_url} onChange={(value) => set("source_url", value)} /><Field label="Source provider" value={form.source_provider} onChange={(value) => set("source_provider", value)} /></> : null}<label className="full"><span>Reason</span><textarea value={form.reason} onChange={(event) => set("reason", event.target.value)} /></label></div>{error ? <div className="admin-error">{error}</div> : null}<footer><button type="button" onClick={onClose}>Cancel</button><button className="admin-primary-button" disabled={saving || !form.display_name.trim() || !form.reason.trim() || (mode === "add" && !form.source_url.trim())} type="button" onClick={() => void save()}>{saving ? "Saving..." : "Save"}</button></footer></div></div>;
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) { return <label><span>{label}</span><input value={value} onChange={(event) => onChange(event.target.value)} /></label>; }

function DeleteDialog({ api, detail, onClose, onDeleted }: { api: ApiClient; detail: AdminBusinessDetail; onClose: () => void; onDeleted: () => void }) {
  const [confirmation, setConfirmation] = useState(""); const [reason, setReason] = useState(""); const [error, setError] = useState(""); const [dependencyMap, setDependencyMap] = useState<Record<string, number> | null>(null);
  useEffect(() => { void api.getAdminBusinessDeleteDependencies(detail.id).then(setDependencyMap).catch((cause) => setError(cause instanceof Error ? cause.message : String(cause))); }, [api, detail.id]);
  const dependencies = useMemo(() => Object.entries(dependencyMap || {}), [dependencyMap]);
  const remove = async () => { try { await api.deleteAdminBusiness(detail.id, confirmation, reason); onDeleted(); } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); } };
  return <div className="admin-dialog-backdrop"><div className="admin-dialog admin-delete-dialog" role="dialog" aria-modal="true"><header><div><h2>Delete business permanently</h2><p>Use Archive for records that have evidence or workflow history.</p></div><button className="admin-icon-button" type="button" onClick={onClose}><X size={16} /></button></header>{dependencyMap === null ? <div className="admin-dependency-warning"><RefreshCw className="sl-spin-icon" size={16} /><div><strong>Checking related records</strong></div></div> : dependencies.length ? <div className="admin-dependency-warning"><CircleAlert size={16} /><div><strong>Permanent deletion is blocked</strong><p>{dependencies.map(([key, value]) => `${key}: ${value}`).join(" · ")}</p></div></div> : null}<Field label={`Type “${detail.display_name}”`} value={confirmation} onChange={setConfirmation} /><label><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>{error ? <div className="admin-error">{error}</div> : null}<footer><button type="button" onClick={onClose}>Cancel</button><button className="admin-danger-button" disabled={dependencyMap === null || Boolean(dependencies.length) || confirmation !== detail.display_name || !reason.trim()} type="button" onClick={() => void remove()}><Trash2 size={14} /> Delete permanently</button></footer></div></div>;
}
