import { Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAppData } from "../state/app-data";
import { useToast } from "../shared-ui";
import type { SourceProvider, SourceRequestSource } from "../types/domain";

const providerCatalog: SourceProvider[] = [
  { id: "google_places", label: "Google Places", configured: false, detail: "Local businesses" },
  { id: "apify_actor", label: "Kijiji / marketplace", configured: false, detail: "Classifieds and source-specific actors" },
  { id: "directories", label: "Directories", configured: false, detail: "Trade associations and business directories" },
  { id: "website_list", label: "Website list", configured: false, detail: "Known websites or imported lists" },
];

export function OverviewScreen() {
  const {
    selectedProduct,
    selectedProductId,
    runSourceRequest,
    sourceProviders,
  } = useAppData();
  const { showToast } = useToast();
  const [selectedSources, setSelectedSources] = useState<SourceRequestSource[]>(["google_places"]);
  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const visibleProviders = useMemo(() => mergeSourceProviders(sourceProviders), [sourceProviders]);
  const selectedProviderCount = selectedSources.length;
  const selectedProviderLabels = visibleProviders
    .filter((provider) => selectedSources.includes(provider.id))
    .map((provider) => provider.label);
  const selectedUnconfiguredProvider = visibleProviders.find(
    (provider) => selectedSources.includes(provider.id) && !provider.configured,
  );

  useEffect(() => {
    if (!visibleProviders.length) return;
    setSelectedSources((current) => {
      const validSelected = current.filter((sourceId) =>
        visibleProviders.some((provider) => provider.id === sourceId && provider.configured),
      );
      if (validSelected.length) return validSelected;
      const firstConfigured = visibleProviders.find((provider) => provider.configured);
      return firstConfigured ? [firstConfigured.id] : [];
    });
  }, [visibleProviders]);

  const submitSourceRequest = async () => {
    const request = prompt.trim();
    if (!selectedProductId || !request || running || !selectedProviderCount) return;
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
          title: "List created",
          message: `Added a saved list from ${selectedProviderLabels.join(" + ")}`,
          tone: "green",
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Source request failed", message, tone: "red" });
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <section className="finder-stage">
        <header className="finder-hero">
          <h1>Who are {selectedProduct ? `${selectedProduct.product_name}'s` : "this product's"} customers?</h1>
          <p>Tell ScoutLead what kind of businesses to look for. Pick the sources that should contribute.</p>
        </header>
        <form
          className="source-request-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submitSourceRequest();
          }}
        >
          <div className="source-prompt-box">
            <label className="prompt-field">
              <span>Find contacts for...</span>
              <textarea
                placeholder="Example: independent residential painters in Toronto with a website, quote request form, strong reviews, and owner contact details"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
              />
            </label>

            <div className="source-picker">
              <div>
                <span>Sources</span>
                <small>Use more than one source when coverage matters.</small>
              </div>
              <div className="source-checkbox-list">
                {visibleProviders.map((provider) => (
                  <SourceCheckbox
                    provider={provider}
                    key={provider.id}
                    checked={selectedSources.includes(provider.id)}
                    onToggle={() => {
                      if (!provider.configured) return;
                      setSelectedSources((current) =>
                        current.includes(provider.id)
                          ? current.filter((sourceId) => sourceId !== provider.id)
                          : [...current, provider.id],
                      );
                    }}
                  />
                ))}
              </div>
            </div>

            <div className="source-request-actions">
              <span>
                {selectedUnconfiguredProvider
                  ? `${selectedUnconfiguredProvider.label} needs setup before it can run.`
                  : selectedProviderCount
                    ? `${selectedProviderCount} source${selectedProviderCount === 1 ? "" : "s"} selected`
                    : "Select at least one source"}
              </span>
              <button
                disabled={
                  !selectedProductId ||
                  !prompt.trim() ||
                  running ||
                  !selectedProviderCount ||
                  Boolean(selectedUnconfiguredProvider)
                }
                type="submit"
              >
                <Play size={14} />
                {running ? "Finding..." : `Find contacts`}
              </button>
            </div>
          </div>
        </form>
      </section>
    </>
  );
}

function SourceCheckbox({
  provider,
  checked,
  onToggle,
}: {
  provider: SourceProvider;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label className={!provider.configured ? "source-checkbox disabled" : checked ? "source-checkbox selected" : "source-checkbox"}>
      <input checked={checked} disabled={!provider.configured} onChange={onToggle} type="checkbox" />
      <span>
        <strong>{provider.label}</strong>
        {provider.detail ? <small>{provider.detail}</small> : null}
      </span>
      {!provider.configured ? <em>Setup needed</em> : null}
    </label>
  );
}

function mergeSourceProviders(providers: SourceProvider[]) {
  const byId = new Map<string, SourceProvider>();
  for (const provider of providerCatalog) byId.set(provider.id, provider);
  for (const provider of providers) {
    const catalogProvider = byId.get(provider.id);
    const label =
      provider.id === "apify_actor" && provider.label.toLowerCase() === "apify actor" && catalogProvider
        ? catalogProvider.label
        : provider.label;
    byId.set(provider.id, {
      ...catalogProvider,
      ...provider,
      label,
      detail: provider.detail || catalogProvider?.detail || null,
    });
  }
  return Array.from(byId.values());
}
