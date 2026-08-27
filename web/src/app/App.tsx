import { Check, ChevronDown, Menu, Plus, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { renderScreen } from "../routes/screen-router";
import { TraceDebugScreen } from "../screens/TraceDebugScreen";
import { Modal, ToastProvider, useToast } from "../shared-ui";
import { AppDataProvider, useAppData } from "../state/app-data";
import type { DiscoveryRun, Product, SourceProvider, SourceRequestSource } from "../types/domain";
import type { Screen } from "../types/navigation";
import { mergeSourceProviders } from "../utils/source-providers";

export function App() {
  return (
    <ToastProvider>
      <AppDataProvider>
        <AppShell />
      </AppDataProvider>
    </ToastProvider>
  );
}

function AppShell() {
  const [activeScreen, setActiveScreen] = useState<Screen>("overview");
  const [isCreatingProduct, setIsCreatingProduct] = useState(false);
  const [openContextMenu, setOpenContextMenu] = useState<"product" | null>(null);
  const [showSourceSettings, setShowSourceSettings] = useState(false);
  const [mobileRailOpen, setMobileRailOpen] = useState(false);
  const [routePath, setRoutePath] = useState(() => window.location.pathname);
  const contextMenuRef = useRef<HTMLDivElement | null>(null);
  const { showToast } = useToast();
  const {
    apiHealthy,
    loading,
    error,
    products,
    selectedProductId,
    setSelectedProductId,
    selectedDiscoveryRunId,
    setSelectedDiscoveryRunId,
    productDiscoveryRuns,
    sourceProviders,
    activeSourceIds,
    setActiveSourceIds,
    createProductFromDescription,
    refreshSnapshot,
  } = useAppData();
  const allSourceProviders = mergeSourceProviders(sourceProviders);
  const connectedProviders = allSourceProviders.filter((provider) => provider.configured);
  const activeSourceProviders = connectedProviders.filter((provider) => activeSourceIds.includes(provider.id));
  const connectedSourceCount = activeSourceProviders.length;
  const sourceStatusLabel =
    connectedSourceCount === 1 ? "1 source connected" : `${connectedSourceCount} sources connected`;
  const sourceDetailLabel = activeSourceProviders.map((provider) => provider.label).join(", ") || "No source enabled";
  const selectedProduct = products.find((product) => product.id === selectedProductId);
  const selectedProductName = selectedProduct ? displayProductName(selectedProduct) : "No product";
  const isTraceRoute = routePath === "/trace" || routePath === "/debug/trace";

  const returnToApp = () => {
    window.history.pushState(null, "", "/");
    setRoutePath("/");
  };

  const startNewProduct = () => {
    if (isTraceRoute) returnToApp();
    setOpenContextMenu(null);
    setMobileRailOpen(false);
    setIsCreatingProduct(true);
  };

  const selectScreen = (screen: Screen) => {
    if (isTraceRoute) returnToApp();
    setActiveScreen(screen);
    setMobileRailOpen(false);
  };

  const selectProduct = (productId: string) => {
    setOpenContextMenu(null);
    setIsCreatingProduct(false);
    setSelectedProductId(productId);
    setSelectedDiscoveryRunId("");
    setActiveScreen("overview");
    setMobileRailOpen(false);
  };

  useEffect(() => {
    if (!error) return;
    showToast({ title: "Request failed", message: error, tone: "red" });
  }, [error, showToast]);

  useEffect(() => {
    const closeMenu = (event: MouseEvent) => {
      if (!contextMenuRef.current?.contains(event.target as Node)) {
        setOpenContextMenu(null);
      }
    };
    document.addEventListener("mousedown", closeMenu);
    return () => document.removeEventListener("mousedown", closeMenu);
  }, []);

  useEffect(() => {
    const handlePopState = () => setRoutePath(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (activeScreen !== "results") return;
    const hasSelectedRun = productDiscoveryRuns.some((run) => run.id === selectedDiscoveryRunId);
    if (!hasSelectedRun) setActiveScreen("overview");
  }, [activeScreen, productDiscoveryRuns, selectedDiscoveryRunId]);

  return (
    <div className={mobileRailOpen ? "console rail-open" : "console"}>
      <header className="mobile-topbar">
        <button
          aria-label={mobileRailOpen ? "Close menu" : "Open menu"}
          className="mobile-icon-button"
          type="button"
          onClick={() => setMobileRailOpen((open) => !open)}
        >
          <Menu size={18} />
        </button>
        <span className="brand-mark">S</span>
        <strong>{selectedProduct ? selectedProductName : "ScoutLead"}</strong>
        <button
          aria-label="New contact list"
          className="mobile-icon-button mobile-add-button"
          type="button"
          onClick={() => {
            setSelectedDiscoveryRunId("");
            selectScreen("overview");
          }}
        >
          <Plus size={18} />
        </button>
      </header>

      {mobileRailOpen ? (
        <button
          aria-label="Close menu"
          className="mobile-rail-backdrop"
          type="button"
          onClick={() => setMobileRailOpen(false)}
        />
      ) : null}

      <aside className="rail">
        <div className="brand">
          <span className="brand-mark">S</span>
          <div>
            <strong>ScoutLead</strong>
            <span>Discovery Console</span>
          </div>
        </div>

        <div className="rail-product" ref={contextMenuRef}>
          <div className={openContextMenu === "product" ? "context-menu-control product-selector is-open" : "context-menu-control product-selector"}>
            <button
              className="rail-product-trigger"
              type="button"
              aria-expanded={openContextMenu === "product"}
              onClick={() => setOpenContextMenu(openContextMenu === "product" ? null : "product")}
            >
              <span>
                <strong>{selectedProductName}</strong>
                <small>{selectedProduct?.value_proposition || selectedProduct?.product_description || "Product profile"}</small>
              </span>
              <ChevronDown className="product-selector-caret" size={15} />
            </button>
            {openContextMenu === "product" ? (
              <div className="context-menu-panel product-menu-panel rail-product-menu">
                {products.length ? (
                  products.map((product) => (
                    <button
                      className={product.id === selectedProductId ? "context-menu-option active" : "context-menu-option"}
                      key={product.id}
                      type="button"
                      onClick={() => selectProduct(product.id)}
                    >
                      <strong>{displayProductName(product)}</strong>
                      <Check className="product-selector-check" size={14} />
                    </button>
                  ))
                ) : (
                  <p className="context-menu-empty">No products yet</p>
                )}
                <button className="context-menu-create" type="button" onClick={startNewProduct}>
                  <Plus size={14} />
                  Add product
                </button>
              </div>
            ) : null}
          </div>
        </div>

        <nav className="list-nav" aria-label="Contact lists">
          <div className="list-nav-header">
            <p>Run history</p>
            <button
              aria-label="New contact list"
              className={!isTraceRoute && activeScreen === "overview" ? "rail-add-list active" : "rail-add-list"}
              type="button"
              onClick={() => {
                setSelectedDiscoveryRunId("");
                selectScreen("overview");
              }}
            >
              <Plus size={16} />
            </button>
          </div>

          <div className="list-nav-section">
            {productDiscoveryRuns.slice(0, 12).map((run) => {
              const title = listLabel(run);
              return (
                <button
                  className={!isTraceRoute && activeScreen === "results" && selectedDiscoveryRunId === run.id ? "list-row active" : "list-row"}
                  key={run.id}
                  title={getRunPrompt(run) || title}
                  type="button"
                  onClick={() => {
                    setSelectedDiscoveryRunId(run.id);
                    void refreshSnapshot(run.id);
                    selectScreen("results");
                  }}
                >
                  <span className="list-run-marker" />
                  <span>
                    <strong>{title}</strong>
                    <small>
                      <span>{listMeta(run, allSourceProviders)}</span>
                      <em>{formatRunDate(run.created_at)}</em>
                    </small>
                  </span>
                </button>
              );
            })}
          </div>
        </nav>

        <div className="rail-status source-status">
          <span className={apiHealthy && connectedSourceCount ? "health good" : "health warn"}>
            <span>
              <i />
              <strong>{apiHealthy && connectedSourceCount ? sourceStatusLabel : "Sources need setup"}</strong>
            </span>
            <small>{apiHealthy && connectedSourceCount ? sourceDetailLabel : "Connect a source to run searches"}</small>
          </span>
          <button aria-label="Source settings" className="rail-settings" type="button" onClick={() => setShowSourceSettings(true)}>
            <SlidersHorizontal size={14} />
          </button>
        </div>
      </aside>

      <section className="main">
        {error && <div className="app-banner">{error}</div>}
        {loading && <div className="app-banner info">Loading data...</div>}
        <main className="content">
          {isTraceRoute ? (
            <TraceDebugScreen onExit={returnToApp} />
          ) : (
            renderScreen(activeScreen)
          )}
        </main>
      </section>

      {isCreatingProduct ? (
        <AddProductDialog
          products={products}
          onClose={() => setIsCreatingProduct(false)}
          onCreate={async (input) => {
            const created = await createProductFromDescription(input);
            if (created) {
              setSelectedProductId(created.id);
              setSelectedDiscoveryRunId("");
              setActiveScreen("overview");
            }
            return created;
          }}
        />
      ) : null}

      {showSourceSettings ? (
        <SourceSettingsDialog
          activeSourceIds={activeSourceIds}
          providers={allSourceProviders}
          onChange={setActiveSourceIds}
          onClose={() => setShowSourceSettings(false)}
        />
      ) : null}
    </div>
  );
}

function AddProductDialog({
  products,
  onClose,
  onCreate,
}: {
  products: Product[];
  onClose: () => void;
  onCreate: (input: { product_name: string; description: string }) => Promise<Product | null>;
}) {
  const { showToast } = useToast();
  const [productName, setProductName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [localError, setLocalError] = useState("");
  const normalizedProductName = productName.trim().toLowerCase();
  const hasDuplicateProductName =
    normalizedProductName.length > 0 &&
    products.some((product) => product.product_name.trim().toLowerCase() === normalizedProductName);
  const canCreateProduct =
    productName.trim().length > 0 &&
    description.trim().length >= 20 &&
    !hasDuplicateProductName &&
    !creating;

  const submit = async () => {
    if (!canCreateProduct) return;
    setCreating(true);
    setLocalError("");
    try {
      const created = await onCreate({
        product_name: productName.trim(),
        description: description.trim(),
      });
      if (!created) {
        showToast({ title: "Product was not created", message: "Check the product details and try again.", tone: "red" });
        return;
      }
      showToast({
        title: "Product created",
        message: "Use the product selector to run searches for this product.",
        tone: "green",
      });
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setLocalError(message);
      showToast({ title: "Product was not created", message, tone: "red" });
    } finally {
      setCreating(false);
    }
  };

  return (
    <Modal title="Add product" onClose={onClose}>
      <form
        className="add-product-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label className="field">
          <span>Product name</span>
          <input
            autoFocus
            placeholder="Product name"
            value={productName}
            onChange={(event) => setProductName(event.target.value)}
          />
          {hasDuplicateProductName ? <em>A product with this name already exists.</em> : null}
        </label>
        <label className="field">
          <span>Product description</span>
          <textarea
            placeholder="Describe what the product does, who it is for, and any search context that matters."
            rows={4}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        {localError ? <p className="form-error">{localError}</p> : null}
        <div className="dialog-actions">
          <button className="secondary" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="runbtn" disabled={!canCreateProduct} type="submit">
            {creating ? "Creating..." : "Create product"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function SourceSettingsDialog({
  activeSourceIds,
  providers,
  onChange,
  onClose,
}: {
  activeSourceIds: SourceRequestSource[];
  providers: SourceProvider[];
  onChange: (sourceIds: SourceRequestSource[]) => void;
  onClose: () => void;
}) {
  const { showToast } = useToast();
  const configuredProviders = providers.filter((provider) => provider.configured);

  const toggleProvider = (provider: SourceProvider) => {
    if (!provider.configured) {
      showToast({
        title: "Source is not configured",
        message: "Connect this provider before enabling it for searches.",
        tone: "amber",
      });
      return;
    }

    const isActive = activeSourceIds.includes(provider.id);
    if (isActive && activeSourceIds.filter((sourceId) => configuredProviders.some((item) => item.id === sourceId)).length <= 1) {
      showToast({
        title: "Keep one source enabled",
        message: "ScoutLead needs at least one connected source to run a search.",
        tone: "amber",
      });
      return;
    }

    onChange(isActive ? activeSourceIds.filter((sourceId) => sourceId !== provider.id) : [...activeSourceIds, provider.id]);
  };

  return (
    <div className="source-dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="source-dialog-card"
        role="dialog"
        aria-modal="true"
        aria-label="Sources"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <h2>Sources</h2>
            <p>Choose which connected sources ScoutLead uses when finding contacts.</p>
          </div>
          <button className="drawer-close" type="button" aria-label="Close sources" onClick={onClose}>
            <X size={18} />
          </button>
        </header>

        <div className="source-toggle-list">
          {configuredProviders.length ? configuredProviders.map((provider) => {
            const active = activeSourceIds.includes(provider.id) && provider.configured;
            return (
              <button
                className={`source-toggle-row${active ? " active" : ""}`}
                key={provider.id}
                type="button"
                onClick={() => toggleProvider(provider)}
              >
                <span>
                  <strong>{provider.label}</strong>
                  <small>{provider.detail || (provider.configured ? "Ready for searches" : "Setup required")}</small>
                </span>
                <em aria-hidden="true">
                  <i />
                </em>
              </button>
            );
          }) : (
            <p className="context-menu-empty">No source providers are configured.</p>
          )}
        </div>

        <footer>
          <span>
            {activeSourceIds.filter((sourceId) => configuredProviders.some((provider) => provider.id === sourceId)).length || 0} enabled
          </span>
        </footer>
      </section>
    </div>
  );
}

function displayProductName(product: Product) {
  const savedName = product.product_name.trim();
  if (savedName && !/^(new product|untitled product|product)$/i.test(savedName)) return savedName;
  const text = product.product_description.trim();
  const labeledName = text.match(
    /(?:one-liner|short(?:\s*\([^)]*\))?|headline)\s*:\s*([A-Z][A-Za-z0-9._-]{1,60})\b/i,
  );
  if (labeledName?.[1]) return labeledName[1];
  const sentenceStartName = text.match(
    /^([A-Z][A-Za-z0-9._-]{1,60})\s+(?:is|helps|turns|lets|allows|enables|gives|provides)\b/,
  );
  return sentenceStartName?.[1] || savedName || "Unnamed product";
}

function listLabel(run: DiscoveryRun) {
  const intent = run.source_inputs?.source_request_intent;
  if (isRecord(intent)) {
    const category = typeof intent.business_category === "string" ? intent.business_category.trim() : "";
    const location = typeof intent.location === "string" ? intent.location.trim() : "";
    if (category && location) return truncateLabel(`${titleCase(category)} · ${titleCase(location)}`, 38);
    if (category) return truncateLabel(titleCase(category), 38);
  }
  const prompt = getRunPrompt(run);
  if (prompt) return truncateLabel(titleFromQuery(prompt) || prompt, 38);
  if (run.name) return truncateLabel(run.name, 38);
  return "Untitled list";
}

function listMeta(run: DiscoveryRun, providers: SourceProvider[]) {
  const source = run.source_inputs?.source_request_source;
  const sourceLabel =
    typeof source === "string"
      ? providers.find((provider) => provider.id === source)?.label || titleCase(source.replace(/_/g, " "))
      : "";
  const status = run.status.replace(/_/g, " ");
  return sourceLabel ? `${status} · ${sourceLabel}` : status;
}

function truncateLabel(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}…` : value;
}

function formatRunDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function titleFromQuery(query: string) {
  const clean = query
    .replace(/^(list|find|get|show|search for)\s+/i, "")
    .replace(/\bcontacts?\b/gi, "")
    .replace(/^(independent|local|small)\s+/i, "")
    .trim();
  const match = clean.match(/^(.+?)\s+(?:in|near|around)\s+(.+?)(?:\s+(?:with|that|who|which|where)\b|$)/i);
  if (!match) return "";
  const subject = match[1]
    .replace(/\bcontacts?\b/gi, "")
    .replace(/\bcompanies\b/gi, "businesses")
    .trim();
  const location = match[2].replace(/[,.].*$/, "").trim();
  if (!subject || !location) return "";
  return `${titleCase(subject)} · ${titleCase(location)}`;
}

function getRunPrompt(run: DiscoveryRun) {
  const prompt = run.source_inputs?.source_request_prompt;
  if (typeof prompt === "string" && prompt.trim()) return prompt.trim();
  const compiledQuery = run.source_inputs?.compiled_query;
  if (typeof compiledQuery === "string" && compiledQuery.trim() && !compiledQuery.startsWith("http")) {
    return compiledQuery.trim();
  }
  if (run.source_input?.trim() && !run.source_input.trim().startsWith("http")) return run.source_input.trim();
  return "";
}

function titleCase(value: string) {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => `${word.slice(0, 1).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
