import { ArrowRight, Plus, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAppData } from "../state/app-data";
import { useToast } from "../shared-ui";
import type {
  DiscoveryRun,
  SearchCriterionMode,
  SearchIntent,
  SearchIntentCriterion,
} from "../types/domain";
import { searchDiscoveryTemplates } from "../utils/template-search";
import { searchIntentFromRun } from "../components/SearchIntentChips";

export function OverviewScreen({
  draftRunName,
  emptyMessage,
  onRunCreated,
}: {
  draftRunName?: string;
  emptyMessage?: string;
  onRunCreated?: (run: DiscoveryRun) => void;
}) {
  const {
    runSourceRequest,
    selectedDiscoveryRun,
    selectedDiscoveryRunId,
    selectedProduct,
    selectedProductId,
  } = useAppData();
  const { showToast } = useToast();
  const [prompt, setPrompt] = useState("");
  const [businessCategory, setBusinessCategory] = useState("");
  const [location, setLocation] = useState("");
  const [criteria, setCriteria] = useState<SearchIntentCriterion[]>([]);
  const [criterionMode, setCriterionMode] = useState<SearchCriterionMode>("required");
  const [criterionText, setCriterionText] = useState("");
  const [contactRequirement, setContactRequirement] = useState("");
  const [applyProductDefaults, setApplyProductDefaults] = useState(true);
  const [running, setRunning] = useState(false);
  const promptValue = prompt.trim();
  const structuredReady = Boolean(businessCategory.trim() && location.trim());
  const structuredIntent = useMemo(
    () =>
      structuredReady
        ? buildStructuredIntent({
            businessCategory,
            location,
            criteria,
            contactRequirement,
            prompt,
          })
        : null,
    [businessCategory, contactRequirement, criteria, location, prompt, structuredReady],
  );
  const promptTemplates = useMemo(
    () => searchDiscoveryTemplates({ product: selectedProduct, limit: 3 }),
    [selectedProduct],
  );
  const ready = Boolean(selectedProductId && (structuredReady || promptValue.length >= 4));

  useEffect(() => {
    const savedIntent = selectedDiscoveryRunId ? searchIntentFromRun(selectedDiscoveryRun) : null;
    setPrompt(selectedDiscoveryRunId ? getRunPrompt(selectedDiscoveryRun) : "");
    setBusinessCategory(savedIntent?.business_category || "");
    setLocation(savedIntent?.location || "");
    setCriteria(
      savedIntent?.criteria.filter(
        (criterion) =>
          !criterion.id.startsWith("product_") && criterion.id !== "user_search_request",
      ) || [],
    );
    setContactRequirement(savedIntent?.contact_requirements[0] || "");
    setApplyProductDefaults(
      selectedDiscoveryRun?.source_inputs?.apply_product_defaults !== false,
    );
  }, [selectedDiscoveryRunId, selectedDiscoveryRun]);

  const addCriterion = () => {
    const description = criterionText.trim();
    if (!description) return;
    setCriteria((current) => [
      ...current,
      {
        id: `user_${Date.now()}_${current.length + 1}`,
        description,
        mode: criterionMode,
        evidence_requirement: "Current public business evidence",
      },
    ]);
    setCriterionText("");
  };

  const submitSourceRequest = async (nextPrompt = prompt) => {
    const request = nextPrompt.trim() || structuredIntent?.search_query || "";
    if (running) return;
    if (!selectedProductId) {
      showToast({ title: "Select a product", message: "Create or choose a product before running discovery.", tone: "amber" });
      return;
    }
    if (!structuredReady && (businessCategory.trim() || location.trim())) {
      showToast({
        title: "Complete the search scope",
        message: "Add both a business category and a location.",
        tone: "amber",
      });
      return;
    }
    if (request.length < 4) {
      showToast({ title: "Enter a search prompt", message: "Describe the businesses to find before running discovery.", tone: "amber" });
      return;
    }
    const requestedName = draftRunName?.trim();
    setRunning(true);
    showToast({
      title: "Search started",
      message: "Checking the business index for existing matches.",
      tone: "blue",
    });
    try {
      const result = await runSourceRequest({
        product_id: selectedProductId,
        source: "auto",
        name: requestedName && !isDraftPlaceholder(requestedName) ? requestedName : undefined,
        prompt: request,
        max_results: 25,
        run_immediately: true,
        business_category: structuredIntent?.business_category,
        geography: structuredIntent?.location,
        apply_product_defaults: applyProductDefaults,
        intent_override: structuredIntent || undefined,
      });
      if (result) {
        const foundCount = result.current_result_count;
        const criteriaMessage = searchCriteriaMessage(result);
        showToast({
          title: "Search ready",
          message: criteriaMessage || `${foundCount} indexed match${foundCount === 1 ? "" : "es"} ready.`,
          tone: criteriaMessage ? "amber" : foundCount ? "green" : "blue",
        });
        onRunCreated?.(result.run);
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
            {running ? (
              <span className="composer-hint" role="status">
                Finding contacts...
              </span>
            ) : promptValue.length > 0 && promptValue.length < 4 ? (
              <span className="composer-hint">Type at least 4 characters</span>
            ) : null}
            <button
              aria-label={running ? "Finding contacts" : "Find contacts"}
              className="composer-submit icon-run"
              disabled={!ready || running}
              title={running ? "Finding contacts" : "Find contacts"}
              type="submit"
            >
              <ArrowRight size={14} />
            </button>
          </div>
        </div>

        <div className="structured-search-builder">
          <div className="structured-search-fields">
            <label>
              <span>Business category</span>
              <input
                onChange={(event) => setBusinessCategory(event.target.value)}
                placeholder="Residential painting contractors"
                value={businessCategory}
              />
            </label>
            <label>
              <span>Location</span>
              <input
                onChange={(event) => setLocation(event.target.value)}
                placeholder="Toronto, Ontario"
                value={location}
              />
            </label>
            <label>
              <span>Required contact</span>
              <select
                onChange={(event) => setContactRequirement(event.target.value)}
                value={contactRequirement}
              >
                <option value="">Any</option>
                <option value="any_contact">Phone or email</option>
                <option value="email">Email</option>
                <option value="phone">Phone</option>
              </select>
            </label>
          </div>

          <div className="criterion-builder">
            <select
              aria-label="Criterion type"
              onChange={(event) => setCriterionMode(event.target.value as SearchCriterionMode)}
              value={criterionMode}
            >
              <option value="required">Must match</option>
              <option value="alternative">Preferred</option>
              <option value="excluded">Exclude</option>
            </select>
            <input
              aria-label="Custom search criterion"
              onChange={(event) => setCriterionText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addCriterion();
                }
              }}
              placeholder="Add a custom criterion"
              value={criterionText}
            />
            <button
              aria-label="Add search criterion"
              disabled={!criterionText.trim()}
              onClick={addCriterion}
              title="Add search criterion"
              type="button"
            >
              <Plus size={14} />
            </button>
          </div>

          {criteria.length || contactRequirement ? (
            <div className="structured-criteria" aria-label="Search criteria">
              {criteria.map((criterion) => (
                <span className={`search-intent-chip is-${criterion.mode}`} key={criterion.id}>
                  {criterion.description}
                  <button
                    aria-label={`Remove ${criterion.description}`}
                    onClick={() =>
                      setCriteria((current) => current.filter((item) => item.id !== criterion.id))
                    }
                    title={`Remove ${criterion.description}`}
                    type="button"
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
              {contactRequirement ? (
                <span className="search-intent-chip is-contact">
                  Contact: {contactRequirement.replace("_", " ")}
                  <button
                    aria-label="Remove contact requirement"
                    onClick={() => setContactRequirement("")}
                    title="Remove contact requirement"
                    type="button"
                  >
                    <X size={12} />
                  </button>
                </span>
              ) : null}
            </div>
          ) : null}

          <div className="product-defaults-row">
            <label>
              <input
                checked={applyProductDefaults}
                onChange={(event) => setApplyProductDefaults(event.target.checked)}
                type="checkbox"
              />
              <span>Use {selectedProduct?.product_name || "product"} defaults</span>
            </label>
            {applyProductDefaults && selectedProduct ? (
              <div className="product-default-summary">
                <span title={selectedProduct.target_customer}>{selectedProduct.target_customer}</span>
                {selectedProduct.ideal_customer_signals.length ? (
                  <span>{selectedProduct.ideal_customer_signals.length} opportunity signals</span>
                ) : null}
                {selectedProduct.exclusions.length ? (
                  <span>{selectedProduct.exclusions.length} exclusions</span>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </form>

      {emptyMessage ? <p className="empty-run-note">{emptyMessage}</p> : null}

      <p className="prompt-template-kicker">Or start from an example</p>
      <section className="prompt-template-grid" aria-label="Search templates">
        {promptTemplates.map((template) => (
          <button
            key={template.id}
            type="button"
            onClick={() => {
              setPrompt(template.query);
              setBusinessCategory("");
              setLocation("");
              setCriteria([]);
              setContactRequirement("");
            }}
          >
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

function searchCriteriaMessage(result: {
  unsupported_criteria: string[];
  unresolved_criteria: string[];
}): string {
  if (result.unsupported_criteria.length) {
    return `Not evaluated: ${result.unsupported_criteria.join(", ")}.`;
  }
  if (result.unresolved_criteria.length) {
    return `Current evidence is missing for: ${result.unresolved_criteria.join(", ")}.`;
  }
  return "";
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

function isDraftPlaceholder(value: string) {
  return /^(?:page name|test|new test\s*\d*|new search(?:\s+\d+)?)$/i.test(value.trim().replace(/\s+/g, " "));
}

function buildStructuredIntent({
  businessCategory,
  location,
  criteria,
  contactRequirement,
  prompt,
}: {
  businessCategory: string;
  location: string;
  criteria: SearchIntentCriterion[];
  contactRequirement: string;
  prompt: string;
}): SearchIntent {
  const category = businessCategory.trim();
  const geography = location.trim();
  const scopeQuery = `${category} in ${geography}`;
  const requestDescription = prompt.trim();
  const effectiveCriteria =
    requestDescription && normalizePhrase(requestDescription) !== normalizePhrase(scopeQuery)
      ? [
          {
            id: "user_search_request",
            description: requestDescription,
            mode: "required" as const,
            evidence_requirement: "Current public business evidence",
          },
          ...criteria,
        ]
      : criteria;
  return {
    schema_version: 1,
    business_category: category,
    location: geography,
    country: "",
    included_subcategories: [],
    criteria: effectiveCriteria,
    contact_requirements: contactRequirement ? [contactRequirement] : [],
    required_signals: [],
    excluded_result_types: [],
    search_query: scopeQuery,
    search_url: "",
    confidence: 100,
    rationale: "User supplied structured search scope and criteria.",
  };
}

function normalizePhrase(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}
