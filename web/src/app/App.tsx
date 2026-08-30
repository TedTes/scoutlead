import { Check, ChevronDown, Download, Menu, Pencil, Plug, Plus, Settings, Trash2, User, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { renderScreen } from "../routes/screen-router";
import { TraceDebugScreen } from "../screens/TraceDebugScreen";
import { Modal, ToastProvider, useToast } from "../shared-ui";
import { AppDataProvider, useAppData } from "../state/app-data";
import type { DiscoveryResult, DiscoveryRun, Product, SourceProvider, SourceRequestSource } from "../types/domain";
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
  const [draftRunName, setDraftRunName] = useState<string | null>(null);
  const [routePath, setRoutePath] = useState(() => window.location.pathname);
  const contextMenuRef = useRef<HTMLDivElement | null>(null);
  const { showToast } = useToast();
  const {
    loading,
    error,
    products,
    selectedProductId,
    setSelectedProductId,
    selectedDiscoveryRunId,
    setSelectedDiscoveryRunId,
    selectedDiscoveryRun,
    productDiscoveryRuns,
    productContacts,
    sourceProviders,
    activeSourceIds,
    setActiveSourceIds,
    createProductFromDescription,
    deleteProduct,
    deleteDiscoveryRuns,
    renameDiscoveryRun,
    refreshSnapshot,
  } = useAppData();
  const allSourceProviders = mergeSourceProviders(sourceProviders);
  const connectedProviders = allSourceProviders.filter((provider) => provider.configured);
  const activeSourceProviders = connectedProviders.filter((provider) => activeSourceIds.includes(provider.id));
  const connectedSourceCount = activeSourceProviders.length;
  const selectedProduct = products.find((product) => product.id === selectedProductId);
  const selectedProductName = selectedProduct ? displayProductName(selectedProduct) : "No product";
  const selectedRunLabel =
    selectedDiscoveryRunId && selectedDiscoveryRun
      ? listLabel(selectedDiscoveryRun)
      : draftRunName?.trim() || "";
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

  const startNewList = () => {
    if (isTraceRoute) returnToApp();
    setOpenContextMenu(null);
    setMobileRailOpen(false);
    setIsCreatingProduct(false);
    setSelectedDiscoveryRunId("");
    setActiveScreen("overview");
    setDraftRunName((current) => current ?? "Page name");
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
    setDraftRunName(null);
    setMobileRailOpen(false);
  };

  const handleDeleteSelectedProduct = async () => {
    if (!selectedProduct) return;
    setOpenContextMenu(null);
    await deleteProduct(selectedProduct.id);
    setSelectedDiscoveryRunId("");
    setActiveScreen("overview");
    setDraftRunName(null);
    showToast({ title: "Product deleted", message: `${selectedProductName} was removed.`, tone: "green" });
  };

  const handleRenameRun = async (runId: string, name: string) => {
    await renameDiscoveryRun(runId, name);
    showToast({ title: "List renamed", tone: "green" });
  };

  const handleDeleteRun = async (run: DiscoveryRun) => {
    const confirmed = window.confirm(`Delete ${listLabel(run)}? This removes the saved results for this run.`);
    if (!confirmed) return;
    await deleteDiscoveryRuns([run.id]);
    if (selectedDiscoveryRunId === run.id) {
      setSelectedDiscoveryRunId("");
      setActiveScreen("overview");
    }
    showToast({ title: "Run deleted", message: "The saved contact list was removed.", tone: "green" });
  };

  const handleExportProductContacts = () => {
    if (!productContacts.length) {
      showToast({
        title: "No contacts to export",
        message: "Run a search before exporting contacts for this product.",
        tone: "amber",
      });
      return;
    }
    exportProductContactsCsv(productContacts, selectedProductName);
    showToast({ title: "Contacts exported", message: `${productContacts.length} contacts downloaded.`, tone: "green" });
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
          aria-label="Account"
          className="mobile-icon-button mobile-avatar-button"
          type="button"
        >
          <User size={17} />
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

        <nav className="list-nav" aria-label="Contact lists">
          <div className="list-nav-header">
            <p>Run history</p>
            <button
              aria-label="New contact search"
              className={!isTraceRoute && activeScreen === "overview" && draftRunName ? "rail-add-list active" : "rail-add-list"}
              type="button"
              onClick={startNewList}
            >
              <Plus size={16} />
            </button>
          </div>

          <div className="list-nav-section">
            {draftRunName !== null ? (
              <RunHistoryDraft value={draftRunName} onChange={setDraftRunName} />
            ) : null}
            {productDiscoveryRuns.slice(0, 12).map((run) => {
              const title = listLabel(run);
              return (
                <RunHistoryItem
                  active={!isTraceRoute && activeScreen === "results" && selectedDiscoveryRunId === run.id}
                  providers={allSourceProviders}
                  run={run}
                  key={run.id}
                  onSelect={() => {
                    setDraftRunName(null);
                    setSelectedDiscoveryRunId(run.id);
                    void refreshSnapshot(run.id);
                    selectScreen("results");
                  }}
                  onRename={handleRenameRun}
                  onDelete={() => void handleDeleteRun(run)}
                  title={title}
                />
              );
            })}
          </div>
        </nav>

        <ProductManagementSection
          connectedSourceCount={connectedSourceCount}
          hasProduct={Boolean(selectedProduct)}
          hasContacts={productContacts.length > 0}
          onDelete={handleDeleteSelectedProduct}
          onExport={handleExportProductContacts}
          onProductSettings={() => selectScreen("product")}
          onSources={() => setShowSourceSettings(true)}
        />
      </aside>

      <section className="main">
        <header className="app-topbar">
          <div className="top-product-area" ref={contextMenuRef}>
            <ProductSelector
              isOpen={openContextMenu === "product"}
              products={products}
              selectedProductId={selectedProductId}
              selectedProductName={selectedProductName}
              selectedRunLabel={selectedRunLabel}
              onAddProduct={startNewProduct}
              onOpenChange={(open) => setOpenContextMenu(open ? "product" : null)}
              onSelectProduct={selectProduct}
            />
            <button className="top-avatar" type="button" aria-label="Account">
              <User size={16} />
            </button>
          </div>
        </header>
        {error && <div className="app-banner">{error}</div>}
        {loading ? (
          <div className="loading-overlay" aria-live="polite">
            <div className="loading-indicator">
              <span className="sl-spin" />
              Loading
            </div>
          </div>
        ) : null}
        <main className="content">
          {isTraceRoute ? (
            <TraceDebugScreen onExit={returnToApp} />
          ) : (
            renderScreen(
              activeScreen,
              selectScreen,
              { isCreatingProduct: false, onCreatingProductChange: setIsCreatingProduct },
              {
                draftRunName: draftRunName ?? undefined,
                onRunCreated: () => {
                  setDraftRunName(null);
                  setActiveScreen("results");
                },
              },
            )
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

function ProductSelector({
  isOpen,
  products,
  selectedProductId,
  selectedProductName,
  selectedRunLabel,
  onAddProduct,
  onOpenChange,
  onSelectProduct,
}: {
  isOpen: boolean;
  products: Product[];
  selectedProductId: string;
  selectedProductName: string;
  selectedRunLabel: string;
  onAddProduct: () => void;
  onOpenChange: (isOpen: boolean) => void;
  onSelectProduct: (productId: string) => void;
}) {
  return (
    <>
      <div className="top-product-cluster">
        <div className={isOpen ? "top-product-control product-selector is-open" : "top-product-control product-selector"}>
          <button
            className="top-product-trigger"
            type="button"
            aria-expanded={isOpen}
            onClick={() => onOpenChange(!isOpen)}
          >
            <span className="top-product-primary">
              <span className="selector-label">Product</span>
              <strong>{selectedProductName}</strong>
              {selectedRunLabel ? <span className="top-product-run">- {selectedRunLabel}</span> : null}
              <ChevronDown className="product-selector-caret" size={15} />
            </span>
          </button>
        {isOpen ? (
          <div className="context-menu-panel product-menu-panel top-product-menu">
            {products.length ? (
              products.map((product) => (
                <button
                  className={product.id === selectedProductId ? "context-menu-option active" : "context-menu-option"}
                  key={product.id}
                  type="button"
                  onClick={() => onSelectProduct(product.id)}
                >
                  <strong>{displayProductName(product)}</strong>
                  <Check className="product-selector-check" size={14} />
                </button>
              ))
            ) : (
              <p className="context-menu-empty">No products yet</p>
            )}
          </div>
        ) : null}
        </div>
        <button className="top-product-add" type="button" aria-label="Add product" onClick={onAddProduct}>
          <Plus size={15} />
        </button>
      </div>
    </>
  );
}

function ProductManagementSection({
  connectedSourceCount,
  hasContacts,
  hasProduct,
  onDelete,
  onExport,
  onProductSettings,
  onSources,
}: {
  connectedSourceCount: number;
  hasContacts: boolean;
  hasProduct: boolean;
  onDelete: () => Promise<void> | void;
  onExport: () => void;
  onProductSettings: () => void;
  onSources: () => void;
}) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const confirmDelete = async () => {
    if (deleting) return;
    setDeleting(true);
    try {
      await onDelete();
      setConfirmingDelete(false);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <section className="mng" aria-label="Product management">
      <p className="mng-label">Manage</p>
      <button className={hasProduct ? "mng-item" : "mng-item is-disabled"} disabled={!hasProduct} type="button" onClick={onProductSettings}>
        <span className="mng-icon">
          <Settings size={13} />
        </span>
        <span className="mng-label-text">Product settings</span>
      </button>
      <button className="mng-item" type="button" onClick={onSources}>
        <span className="mng-icon">
          <Plug size={13} />
        </span>
        <span className="mng-label-text">Sources</span>
        <span className="mng-count">· {connectedSourceCount} connected</span>
      </button>
      <button className={hasContacts ? "mng-item" : "mng-item is-disabled"} disabled={!hasContacts} type="button" onClick={onExport}>
        <span className="mng-icon">
          <Download size={13} />
        </span>
        <span className="mng-label-text">Export all contacts</span>
      </button>
      <div className="mng-divider" />
      {confirmingDelete ? (
        <div className="mng-confirm">
          <div className="q">
            Delete this product and its <b>runs, contacts, and history</b>?
          </div>
          <div className="btns">
            <button className="cancel" type="button" onClick={() => setConfirmingDelete(false)}>
              Cancel
            </button>
            <button className="delete" disabled={deleting} type="button" onClick={() => void confirmDelete()}>
              {deleting ? "Deleting..." : "Delete"}
            </button>
          </div>
        </div>
      ) : (
        <button
          className={hasProduct ? "mng-danger" : "mng-danger is-disabled"}
          disabled={!hasProduct}
          type="button"
          onClick={() => setConfirmingDelete(true)}
        >
          <span className="mng-icon">
            <Trash2 size={13} />
          </span>
          <span className="mng-label-text">Delete product</span>
        </button>
      )}
    </section>
  );
}

function RunHistoryDraft({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="list-row-shell draft active">
      <div className="list-row-editor">
        <span className="list-run-marker" />
        <input
          aria-label="New list name"
          autoFocus
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onFocus={(event) => event.currentTarget.select()}
        />
      </div>
      <small>new search</small>
    </div>
  );
}

function RunHistoryItem({
  active,
  providers,
  run,
  title,
  onDelete,
  onRename,
  onSelect,
}: {
  active: boolean;
  providers: SourceProvider[];
  run: DiscoveryRun;
  title: string;
  onDelete: () => void;
  onRename: (runId: string, name: string) => Promise<void>;
  onSelect: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(title);

  useEffect(() => {
    if (!editing) setName(title);
  }, [editing, title]);

  const commitName = async () => {
    const nextName = name.trim();
    if (!nextName) {
      setName(title);
      setEditing(false);
      return;
    }
    if (nextName !== title) await onRename(run.id, nextName);
    setEditing(false);
  };

  return (
    <div className={active ? "list-row-shell active" : "list-row-shell"} title={getRunPrompt(run) || title}>
      {editing ? (
        <div className="list-row-editor">
          <span className="list-run-marker" />
          <input
            aria-label="Rename run"
            autoFocus
            value={name}
            onBlur={() => void commitName()}
            onChange={(event) => setName(event.target.value)}
            onFocus={(event) => event.currentTarget.select()}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setName(title);
                setEditing(false);
              }
              if (event.key === "Enter") void commitName();
            }}
          />
        </div>
      ) : (
        <button className="list-row-main" type="button" onClick={onSelect} onDoubleClick={() => setEditing(true)}>
          <span className="list-run-marker" />
          <span>
            <strong>{title}</strong>
            <small>
              <span>{listMeta(run, providers)}</span>
              <em>{formatRunDate(run.created_at)}</em>
            </small>
          </span>
        </button>
      )}
      <div className="list-row-actions">
        <button
          aria-label={`Rename ${title}`}
          className="list-row-action"
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            setEditing(true);
          }}
        >
          <Pencil size={12} />
        </button>
        <button
          aria-label={`Delete ${title}`}
          className="list-row-action danger"
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onDelete();
          }}
        >
          <Trash2 size={12} />
        </button>
      </div>
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
  if (run.name && !isGeneratedRunName(run.name)) return truncateLabel(run.name, 38);
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

function isGeneratedRunName(value: string) {
  return /\b(source request|discovery|validation)\b.*\d{4}-\d{2}-\d{2}/i.test(value);
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

function exportProductContactsCsv(contacts: DiscoveryResult[], productName: string) {
  const rows = contacts.map((contact) => ({
    company: contact.company_name,
    email: contact.contact_email || contact.research?.contact_email || "",
    contact_name: contact.research?.contact_name || "",
    phone: rawContactValue(contact, ["phone", "telephone", "contact_phone", "phoneNumber"]),
    website: contact.website_url || contact.research?.website_url || "",
    geography: contact.geography || contact.research?.geography || "",
    source: contact.source,
    score: String(Math.round(contact.qualification?.score ?? contact.research?.confidence ?? 0)),
    status: contact.status,
    summary: contact.research?.summary || contact.description || "",
  }));
  const headers = Object.keys(rows[0] || { company: "" });
  const csv = [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => csvCell(row[header as keyof typeof row])).join(",")),
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${slugify(productName)}-contacts.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function rawContactValue(contact: DiscoveryResult, keys: string[]) {
  const rawSources = contact.raw_sources || [];
  for (const source of rawSources) {
    for (const key of keys) {
      const value = source[key];
      if (typeof value === "string" && value.trim()) return value.trim();
      if (typeof value === "number" && Number.isFinite(value)) return String(value);
    }
  }
  return "";
}

function csvCell(value: string | number | undefined) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}

function slugify(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "contacts";
}
