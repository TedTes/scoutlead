import { Check, ChevronDown, Download, Menu, Pencil, Plus, Settings, Trash2, User } from "lucide-react";
import { useEffect, useRef, useState, type SetStateAction } from "react";
import { renderScreen } from "../routes/screen-router";
import { TraceDebugScreen } from "../screens/TraceDebugScreen";
import { Modal, ToastProvider, useToast } from "../shared-ui";
import { AppDataProvider, useAppData } from "../state/app-data";
import type { DiscoveryResult, DiscoveryRun, Product } from "../types/domain";
import type { Screen } from "../types/navigation";

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
  const [mobileRailOpen, setMobileRailOpen] = useState(false);
  const [draftRunName, setDraftRunNameState] = useState<string | null>(null);
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
    createProductFromDescription,
    deleteProduct,
    deleteDiscoveryRuns,
    renameDiscoveryRun,
    refreshSnapshot,
  } = useAppData();
  const selectedProduct = products.find((product) => product.id === selectedProductId);
  const selectedProductName = selectedProduct ? displayProductName(selectedProduct) : "No product";
  const selectedRunLabel =
    selectedDiscoveryRunId && selectedDiscoveryRun
      ? listLabel(selectedDiscoveryRun)
      : draftRunName?.trim() || "";
  const isTraceRoute = routePath === "/trace" || routePath === "/debug/trace";
  const setDraftRunName = (nextValue: SetStateAction<string | null>) => {
    setDraftRunNameState((current) => {
      const next =
        typeof nextValue === "function"
          ? (nextValue as (value: string | null) => string | null)(current)
          : nextValue;
      writeDraftRunName(selectedProductId, next);
      return next;
    });
  };

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
    setActiveScreen("overview");
    setDraftRunName((current) => current ?? readDraftRunName(selectedProductId) ?? "Page name");
    setSelectedDiscoveryRunId("");
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
    setDraftRunNameState(null);
    setMobileRailOpen(false);
  };

  const handleDeleteSelectedProduct = async () => {
    if (!selectedProduct) return;
    setOpenContextMenu(null);
    await deleteProduct(selectedProduct.id);
    writeDraftRunName(selectedProduct.id, null);
    setDraftRunNameState(null);
    setSelectedDiscoveryRunId("");
    setActiveScreen("overview");
    showToast({ title: "Product deleted", message: `${selectedProductName} was removed.`, tone: "green" });
  };

  const handleRenameRun = async (runId: string, name: string) => {
    await renameDiscoveryRun(runId, name);
    showToast({ title: "List renamed", tone: "green" });
  };

  const handleDeleteRun = async (run: DiscoveryRun) => {
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

  useEffect(() => {
    if (!selectedProductId) {
      setDraftRunNameState(null);
      return;
    }
    setDraftRunNameState(readDraftRunName(selectedProductId));
  }, [selectedProductId]);

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
              <RunHistoryDraft
                active={!isTraceRoute && activeScreen === "overview" && !selectedDiscoveryRunId}
                value={draftRunName}
                onChange={setDraftRunName}
                onSelect={startNewList}
              />
            ) : null}
            {draftRunName === null && productDiscoveryRuns.length === 0 ? (
              <div className="nav-empty">
                <div className="t">No runs yet</div>
                <div className="s">Start a search to create the first saved list.</div>
              </div>
            ) : null}
            {productDiscoveryRuns.map((run) => {
              const title = listLabel(run);
              return (
                <RunHistoryItem
                  active={!isTraceRoute && activeScreen === "results" && selectedDiscoveryRunId === run.id}
                  run={run}
                  key={run.id}
                  onSelect={() => {
                    setSelectedDiscoveryRunId(run.id);
                    void refreshSnapshot(run.id);
                    selectScreen("results");
                  }}
                  onRename={handleRenameRun}
                  onDelete={() => void handleDeleteRun(run)}
                  contacts={productContacts}
                  title={title}
                />
              );
            })}
          </div>
        </nav>

        <ProductManagementSection
          hasProduct={Boolean(selectedProduct)}
          hasContacts={productContacts.length > 0}
          onDelete={handleDeleteSelectedProduct}
          onExport={handleExportProductContacts}
          onProductSettings={() => selectScreen("product")}
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
  hasContacts,
  hasProduct,
  onDelete,
  onExport,
  onProductSettings,
}: {
  hasContacts: boolean;
  hasProduct: boolean;
  onDelete: () => Promise<void> | void;
  onExport: () => void;
  onProductSettings: () => void;
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

function RunHistoryDraft({
  active,
  value,
  onChange,
  onSelect,
}: {
  active: boolean;
  value: string;
  onChange: (value: string) => void;
  onSelect: () => void;
}) {
  const [editing, setEditing] = useState(active);
  const displayName = value.trim() || "Page name";

  useEffect(() => {
    if (!active) {
      setEditing(false);
      return;
    }
    if (displayName === "Page name") setEditing(true);
  }, [active, displayName]);

  const commitName = () => {
    onChange(displayName);
    setEditing(false);
  };

  return (
    <div className={active ? "list-row-shell run draft active is-active" : "list-row-shell run draft"}>
      {editing ? (
        <div className="list-row-editor">
          <span className="run-dot is-new" />
          <input
            aria-label="New list name"
            autoFocus
            value={value}
            onBlur={commitName}
            onChange={(event) => onChange(event.target.value)}
            onFocus={(event) => event.currentTarget.select()}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                event.stopPropagation();
                commitName();
              }
            }}
          />
        </div>
      ) : (
        <button className="list-row-main" type="button" onClick={onSelect} onDoubleClick={() => setEditing(true)}>
          <span className="run-title">{displayName}</span>
          <span className="run-meta">
            <span className="run-dot is-new" />
            <span className="run-yield">new search</span>
            <span className="run-when">draft</span>
          </span>
        </button>
      )}
    </div>
  );
}

function RunHistoryItem({
  active,
  run,
  title,
  contacts,
  onDelete,
  onRename,
  onSelect,
}: {
  active: boolean;
  run: DiscoveryRun;
  title: string;
  contacts: DiscoveryResult[];
  onDelete: () => void | Promise<void>;
  onRename: (runId: string, name: string) => Promise<void>;
  onSelect: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(title);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

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

  const confirmDelete = async () => {
    setDeleting(true);
    try {
      await onDelete();
    } finally {
      setDeleting(false);
      setConfirmingDelete(false);
    }
  };

  return (
    <div className={active ? "list-row-shell run active is-active" : "list-row-shell run"} title={getRunPrompt(run) || title}>
      {editing ? (
        <div className="list-row-editor">
          <span className={`run-dot ${runDotClass(run)}`} />
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
          <span className="run-title">{title}</span>
          <span className="run-meta">
            <span className={`run-dot ${runDotClass(run)}`} />
            <span className="run-yield">{runYield(run, contacts)}</span>
            <span className="run-status">{listMeta(run)}</span>
            <span className="run-when">{formatRunDate(run.created_at)}</span>
          </span>
        </button>
      )}
      {confirmingDelete ? (
        <div className="run-confirm">
          <span className="q">Delete run?</span>
          <button className="yes" type="button" disabled={deleting} onClick={() => void confirmDelete()}>
            Delete
          </button>
          <button type="button" disabled={deleting} onClick={() => setConfirmingDelete(false)}>
            Cancel
          </button>
        </div>
      ) : null}
      <div className="list-row-actions run-actions">
        <button
          aria-label={`Rename ${title}`}
          className="list-row-action run-act"
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            setConfirmingDelete(false);
            setEditing(true);
          }}
        >
          <Pencil size={12} />
        </button>
        <button
          aria-label={`Delete ${title}`}
          className="list-row-action run-act del danger"
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            setEditing(false);
            setConfirmingDelete(true);
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
  if (run.name && !isGeneratedRunName(run.name)) return run.name;
  const intent = run.source_inputs?.source_request_intent;
  if (isRecord(intent)) {
    const category = typeof intent.business_category === "string" ? intent.business_category.trim() : "";
    const location = typeof intent.location === "string" ? intent.location.trim() : "";
    if (category && location) return `${titleCase(category)} · ${titleCase(location)}`;
    if (category) return titleCase(category);
  }
  const prompt = getRunPrompt(run);
  if (prompt) return titleFromQuery(prompt) || prompt;
  if (run.name) return run.name;
  return "Untitled list";
}

function isGeneratedRunName(value: string) {
  return /\b(source request|discovery|validation)\b.*\d{4}-\d{2}-\d{2}/i.test(value);
}

function listMeta(run: DiscoveryRun) {
  const status = run.status.replace(/_/g, " ");
  return status;
}

function runDotClass(run: DiscoveryRun) {
  const status = run.status.toLowerCase();
  if (["discovering", "researching", "qualifying", "drafting_outreach", "sending"].includes(status)) {
    return "is-running";
  }
  if (["draft", "paused"].includes(status)) return "is-new";
  if (status === "failed") return "is-failed";
  return "is-done";
}

function runYield(run: DiscoveryRun, contacts: DiscoveryResult[]) {
  const runContacts = contacts.filter((contact) => contact.campaign_id === run.id);
  const verifiedCount = runContacts.filter((contact) => contact.verification_status === "valid").length;
  if (runContacts.length && verifiedCount) return `${runContacts.length} · ${verifiedCount} verified`;
  if (runContacts.length) return `${runContacts.length} found`;
  if (runDotClass(run) === "is-running") return "searching";
  return "0 found";
}

function formatRunDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function draftRunStorageKey(productId: string) {
  return `draftDiscoveryRunName:${productId}`;
}

function readDraftRunName(productId: string) {
  if (!productId) return null;
  return localStorage.getItem(draftRunStorageKey(productId));
}

function writeDraftRunName(productId: string, value: string | null) {
  if (!productId) return;
  const key = draftRunStorageKey(productId);
  if (value === null) {
    localStorage.removeItem(key);
    return;
  }
  localStorage.setItem(key, value);
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
