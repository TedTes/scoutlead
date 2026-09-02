import { Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAppData } from "../state/app-data";
import { useToast } from "../shared-ui";
import type { SourceRequestSource } from "../types/domain";
import { mergeSourceProviders, normalizeActiveSourceIds } from "../utils/source-providers";
import { searchDiscoveryTemplates } from "../utils/template-search";

export function OverviewScreen({
  draftRunName,
  emptyMessage,
  onRunCreated,
}: {
  draftRunName?: string;
  emptyMessage?: string;
  onRunCreated?: () => void;
}) {
  const {
    runSourceRequest,
    selectedDiscoveryRun,
    selectedDiscoveryRunId,
    selectedProduct,
    selectedProductId,
    sourceProviders,
    activeSourceIds,
  } = useAppData();
  const { showToast } = useToast();
  const [selectedSources, setSelectedSources] = useState<SourceRequestSource[]>(["google_places"]);
  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const providers = useMemo(() => mergeSourceProviders(sourceProviders), [sourceProviders]);
  const connectedProviders = useMemo(() => providers.filter((provider) => provider.configured), [providers]);
  const promptValue = prompt.trim();
  const currentQuery = promptValue || getRunPrompt(selectedDiscoveryRun) || "";
  const promptTags = parsePromptTags(currentQuery);
  const promptTemplates = useMemo(
    () => searchDiscoveryTemplates({ product: selectedProduct, limit: 3 }),
    [selectedProduct],
  );
  const selectedSource = selectedSources[0] || "";
  const ready = Boolean(selectedProductId && promptValue.length >= 4 && selectedSource);

  useEffect(() => {
    setSelectedSources(normalizeActiveSourceIds(activeSourceIds, connectedProviders).slice(0, 1));
  }, [activeSourceIds, connectedProviders]);

  useEffect(() => {
    setPrompt(selectedDiscoveryRunId ? getRunPrompt(selectedDiscoveryRun) : "");
  }, [selectedDiscoveryRunId, selectedDiscoveryRun]);

  const submitSourceRequest = async (nextPrompt = prompt) => {
    const request = nextPrompt.trim();
    if (!selectedProductId || !request || running || !selectedSource) return;
    const requestedName = draftRunName?.trim();
    setRunning(true);
    try {
      const result = await runSourceRequest({
        product_id: selectedProductId,
        source: selectedSource,
        name: requestedName && requestedName.toLowerCase() !== "page name" ? requestedName : undefined,
        prompt: request,
        max_results: 25,
        run_immediately: true,
      });
      if (result) {
        const foundCount = result.summary?.discovered_lead_count ?? 0;
        showToast({
          title: foundCount ? "Search complete" : "Search finished",
          message: foundCount ? `${foundCount} contact${foundCount === 1 ? "" : "s"} found.` : "No contacts were returned. Try another search.",
          tone: foundCount ? "green" : "amber",
        });
        onRunCreated?.();
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Search failed", message, tone: "red" });
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="discovery-workspace">
      <header className="discovery-hero">
        <div>
          <h1>Who should we find?</h1>
          <p>
            Describe the businesses you want to reach. ScoutLead finds them, scores fit against{" "}
            {selectedProduct?.product_name || "your product"}, and pulls reachable contacts.
          </p>
        </div>
      </header>

      <form
        className={running ? "composer-panel is-running" : "composer-panel"}
        onSubmit={(event) => {
          event.preventDefault();
          void submitSourceRequest(prompt);
        }}
      >
        <div className="composer-body">
          <label className="composer-query">
            <span>Search</span>
            <textarea
              aria-label={`Find contacts for ${selectedProduct?.product_name || "selected product"}`}
              placeholder="Independent residential painters in Toronto with a website, quote form, and owner contact"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
            />
          </label>
          <div className="composer-submit-group">
            {!running && promptValue.length > 0 && promptValue.length < 4 ? (
              <span className="composer-hint">Type at least 4 characters</span>
            ) : null}
            <button
              aria-label={running ? "Finding contacts" : "Find contacts"}
              className="composer-submit icon-run"
              disabled={!ready || running}
              title={running ? "Finding contacts" : "Find contacts"}
              type="submit"
            >
              <Play size={14} />
            </button>
          </div>
        </div>

        {promptTags.length ? (
          <div className="composer-tags" aria-label="Search signals">
            {promptTags.map((tag) => (
              <span key={tag}>{tag}</span>
            ))}
          </div>
        ) : null}
      </form>

      {emptyMessage ? <p className="empty-run-note">{emptyMessage}</p> : null}

      <p className="prompt-template-kicker">Or start from an example</p>
      <section className="prompt-template-grid" aria-label="Search templates">
        {promptTemplates.map((template) => (
          <button key={template.id} type="button" onClick={() => setPrompt(template.query)}>
            <strong>
              {template.label}
              <span>{template.tag}</span>
            </strong>
            <small>{template.query}</small>
          </button>
        ))}
      </section>
    </section>
  );
}

function getRunPrompt(run: { source_input?: string | null; source_inputs?: Record<string, unknown> } | undefined) {
  const prompt = run?.source_inputs?.source_request_prompt;
  if (typeof prompt === "string" && prompt.trim()) return prompt.trim();
  const compiledQuery = run?.source_inputs?.compiled_query;
  if (typeof compiledQuery === "string" && compiledQuery.trim() && !compiledQuery.startsWith("http")) {
    return compiledQuery.trim();
  }
  if (run?.source_input?.trim() && !run.source_input.trim().startsWith("http")) return run.source_input.trim();
  return "";
}

function parsePromptTags(prompt: string) {
  const lower = prompt.toLowerCase();
  const tags: string[] = [];
  if (lower.includes("paint")) tags.push("Painting");
  if (lower.includes("hvac")) tags.push("HVAC");
  if (lower.includes("auto")) tags.push("Auto");
  if (lower.includes("toronto")) tags.push("Toronto");
  if (lower.includes("vancouver")) tags.push("Vancouver");
  if (lower.includes("calgary")) tags.push("Calgary");
  if (lower.includes("website")) tags.push("Website");
  if (lower.includes("quote")) tags.push("Quote form");
  if (lower.includes("review")) tags.push("Strong reviews");
  if (lower.includes("owner")) tags.push("Owner contact");
  return tags.slice(0, 8);
}
