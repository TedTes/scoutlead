import { Check, Play, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAppData } from "../state/app-data";
import { useToast } from "../shared-ui";
import type { SourceProvider, SourceRequestSource } from "../types/domain";
import { mergeSourceProviders, normalizeActiveSourceIds } from "../utils/source-providers";

const starterPrompts = [
  {
    label: "Residential painters in Toronto",
    hint: "Local shops with websites and quote forms",
    query: "independent residential painters in Toronto with a website, quote-request form, strong reviews, and owner contact details",
  },
  {
    label: "Small HVAC in Vancouver",
    hint: "Service businesses with direct contact paths",
    query: "small HVAC companies in Vancouver with a website, strong reviews, and reachable owner contact details",
  },
  {
    label: "Auto detailers in Calgary",
    hint: "Owner-led shops with public booking signals",
    query: "independent mobile auto detailers in Calgary with strong reviews, a website, and owner contact details",
  },
];

export function OverviewScreen() {
  const {
    runSourceRequest,
    selectedDiscoveryRun,
    selectedDiscoveryRunId,
    selectedProduct,
    selectedProductId,
    sourceProviders,
    activeSourceIds,
    setActiveSourceIds,
  } = useAppData();
  const { showToast } = useToast();
  const [selectedSources, setSelectedSources] = useState<SourceRequestSource[]>(["google_places"]);
  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const providers = useMemo(() => mergeSourceProviders(sourceProviders), [sourceProviders]);
  const connectedProviders = useMemo(() => providers.filter((provider) => provider.configured), [providers]);
  const selectedProviderLabels = connectedProviders
    .filter((provider) => selectedSources.includes(provider.id))
    .map((provider) => provider.label);
  const promptValue = prompt.trim();
  const currentQuery = promptValue || getRunPrompt(selectedDiscoveryRun) || "";
  const promptTags = parsePromptTags(currentQuery);
  const ready = Boolean(selectedProductId && promptValue.length >= 4 && selectedSources.length);

  useEffect(() => {
    setSelectedSources(normalizeActiveSourceIds(activeSourceIds, connectedProviders));
  }, [activeSourceIds, connectedProviders]);

  useEffect(() => {
    setPrompt(selectedDiscoveryRunId ? getRunPrompt(selectedDiscoveryRun) : "");
  }, [selectedDiscoveryRunId, selectedDiscoveryRun]);

  const submitSourceRequest = async (nextPrompt = prompt) => {
    const request = nextPrompt.trim();
    if (!selectedProductId || !request || running || !selectedSources.length) return;
    setRunning(true);
    try {
      const results = [];
      for (const source of selectedSources) {
        const result = await runSourceRequest({
          product_id: selectedProductId,
          source,
          prompt: request,
          max_results: 25,
          run_immediately: true,
        });
        if (result) results.push(result);
      }
      if (results.length) {
        showToast({
          title: "Search complete",
          message: `Searched ${selectedProviderLabels.join(" + ") || "selected sources"}`,
          tone: "green",
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Search failed", message, tone: "red" });
    } finally {
      setRunning(false);
    }
  };

  const runStarter = (query: string) => {
    setPrompt(query);
    void submitSourceRequest(query);
  };

  return (
    <section className="discovery-workspace">
      <header className="discovery-hero">
        <span className="discovery-hero-icon" aria-hidden="true">
          <Search size={20} />
        </span>
        <h1>Who should we find?</h1>
        <p>
          Describe the shop in plain language. ScoutLead scores each result against this product, source signals, and reachable contact details.
        </p>
      </header>

      <form
        className="composer-panel"
        onSubmit={(event) => {
          event.preventDefault();
          void submitSourceRequest(prompt);
        }}
      >
        <label className="composer-query">
          <span>Search</span>
          <textarea
            aria-label={`Find contacts for ${selectedProduct?.product_name || "selected product"}`}
            placeholder="Independent residential painters in Toronto with a website, quote form, and owner contact"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
          />
        </label>

        {promptTags.length ? (
          <div className="composer-tags" aria-label="Search signals">
            {promptTags.map((tag) => (
              <span key={tag}>{tag}</span>
            ))}
          </div>
        ) : null}

        <div className="composer-footer">
          <div className="source-pill-row">
            <span className="source-label">Sources</span>
            {connectedProviders.map((provider) => (
              <SourceOption
                provider={provider}
                key={provider.id}
                checked={selectedSources.includes(provider.id)}
                onToggle={() => {
                  setSelectedSources((current) => {
                    const next = current.includes(provider.id)
                      ? current.filter((sourceId) => sourceId !== provider.id)
                      : [...current, provider.id];
                    setActiveSourceIds(next);
                    return next;
                  });
                }}
              />
            ))}
          </div>
          <div className="composer-submit-group">
            {!running && promptValue.length > 0 && promptValue.length < 4 ? (
              <span className="composer-hint">Type at least 4 characters</span>
            ) : null}
            <button className="composer-submit" disabled={!ready || running} type="submit">
              <Play size={14} />
              {running ? "Finding..." : "Find contacts"}
            </button>
          </div>
        </div>
      </form>

      <div className="starter-section">
        <span className="starter-section-label">Or start from an example</span>
        <div className="starter-grid">
          {starterPrompts.map((starter) => (
            <button key={starter.label} type="button" onClick={() => runStarter(starter.query)}>
              <strong>{starter.label}</strong>
              <span>{starter.hint}</span>
              <em>Run this search</em>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function SourceOption({
  provider,
  checked,
  onToggle,
}: {
  provider: SourceProvider;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <button className={checked ? "source-pill selected" : "source-pill"} type="button" onClick={onToggle}>
      {checked ? <Check size={13} /> : null}
      {provider.label}
    </button>
  );
}

function getRunPrompt(run: { source_input?: string | null; source_inputs?: Record<string, unknown> } | undefined) {
  const prompt = run?.source_inputs?.source_request_prompt;
  if (typeof prompt === "string" && prompt.trim()) return prompt.trim();
  if (run?.source_input?.trim()) return run.source_input.trim();
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
