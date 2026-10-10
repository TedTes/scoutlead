import {
  CalendarClock,
  Check,
  ChevronDown,
  CircleX,
  Download,
  List,
  LoaderCircle,
  Menu,
  Package,
  Pencil,
  Plug,
  Plus,
  Send,
  Settings,
  Star,
  Trash2,
  User,
  Users,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type SetStateAction,
} from "react";
import { renderScreen } from "../routes/screen-router";
import { TraceDebugScreen } from "../screens/TraceDebugScreen";
import { ExportContactsDialog, Modal, ToastProvider, useToast } from "../shared-ui";
import { AppDataProvider, useAppData } from "../state/app-data";
import type {
  DiscoveryResult,
  DiscoveryRun,
  Product,
  ProductProfileInput,
  Territory,
} from "../types/domain";
import type { LeadWorkflowCounts, LeadWorkflowView, Screen } from "../types/navigation";
import {
  baseExportFileName,
  defaultExportFileName,
  exportContactEmail,
  normalizeExportFileName,
} from "../utils/export-file";

type AppProps = {
  getAuthToken?: () => Promise<string | null>;
  accountSlot?: ReactNode;
  approverLabel?: string;
};

type AppViewMode = "auto" | Screen;

const RAIL_WIDTH_DEFAULT = 244;
const RAIL_WIDTH_MIN = 220;
const RAIL_WIDTH_MAX = 420;
const WORKFLOW_HEIGHT_DEFAULT = 190;
const WORKFLOW_HEIGHT_MIN = 190;
const WORKFLOW_HEIGHT_MAX = 220;
const MANAGE_HEIGHT_DEFAULT = 151;
const MANAGE_HEIGHT_MIN = 112;
const RAIL_FIXED_HEIGHT_BUDGET = 330;

export function App({ getAuthToken, accountSlot, approverLabel }: AppProps = {}) {
  return (
    <ToastProvider>
      <AppDataProvider getAuthToken={getAuthToken} approverLabel={approverLabel}>
        <AppShell accountSlot={accountSlot} />
      </AppDataProvider>
    </ToastProvider>
  );
}

function AppShell({ accountSlot }: { accountSlot?: ReactNode }) {
  const [viewMode, setViewMode] = useState<AppViewMode>("auto");
  const [leadWorkflowView, setLeadWorkflowView] = useState<LeadWorkflowView>("inbox");
  const [workflowSummary, setWorkflowSummary] = useState<{ runId: string; counts: LeadWorkflowCounts } | null>(null);
  const [sourceReviewSummary, setSourceReviewSummary] = useState<{ runId: string; count: number } | null>(null);
  const [workspaceExpanded, setWorkspaceExpanded] = useState(false);
  const [isCreatingProduct, setIsCreatingProduct] = useState(false);
  const [productMenuOpen, setProductMenuOpen] = useState(false);
  const [renameAudience, setRenameAudience] = useState<Territory | null>(null);
  const [deleteAudience, setDeleteAudience] = useState<Territory | null>(null);
  const [mobileRailOpen, setMobileRailOpen] = useState(false);
  const [draftRunName, setDraftRunNameState] = useState<string | null>(null);
  const [exportFileName, setExportFileName] = useState("");
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [routePath, setRoutePath] = useState(() => window.location.pathname);
  const [railWidth, setRailWidth] = useState(() =>
    readStoredDimension("scoutlead:rail-width", RAIL_WIDTH_DEFAULT, RAIL_WIDTH_MIN, RAIL_WIDTH_MAX),
  );
  const [workflowSectionHeight, setWorkflowSectionHeight] = useState(() =>
    readStoredDimension(
      "scoutlead:workflow-height",
      WORKFLOW_HEIGHT_DEFAULT,
      WORKFLOW_HEIGHT_MIN,
      WORKFLOW_HEIGHT_MAX,
    ),
  );
  const [manageSectionHeight, setManageSectionHeight] = useState(() =>
    readStoredDimension("scoutlead:manage-height", MANAGE_HEIGHT_DEFAULT, MANAGE_HEIGHT_MIN, 280),
  );
  const productMenuRef = useRef<HTMLDivElement | null>(null);
  const railRef = useRef<HTMLElement | null>(null);
  const { showToast } = useToast();
  const {
    loading,
    error,
    products,
    selectedProductId,
    setSelectedProductId,
    selectedDiscoveryRunId,
    setSelectedDiscoveryRunId,
    selectedProfileId,
    setSelectedProfileId,
    selectProfile,
    switchingProfileId,
    profileBatch,
    productDiscoveryRuns,
    productContacts,
    territories,
    gmailConnectionStatus,
    createProductFromProfile,
    renameProfile,
    deleteProfile,
    deleteProduct,
    deleteDiscoveryRuns,
    renameDiscoveryRun,
    refreshSnapshot,
  } = useAppData();
  const selectedProduct = products.find((product) => product.id === selectedProductId);
  const selectedProductName = selectedProduct ? displayProductName(selectedProduct) : "No product";
  const productRunLabels = useMemo(
    () => groupedRunLabels(productDiscoveryRuns, territories.filter((territory) => territory.product_id === selectedProductId)),
    [productDiscoveryRuns, selectedProductId, territories],
  );
  const isTraceRoute =
    routePath === "/trace" ||
    routePath === "/debug/trace" ||
    routePath === "/app/trace" ||
    routePath === "/app/debug/trace";
  const productProfiles = territories.filter((profile) => profile.product_id === selectedProductId);
  const selectedRun = productDiscoveryRuns.find((run) => run.id === selectedDiscoveryRunId);
  const selectedRunExists = Boolean(
    selectedProfileId && selectedRun?.territory_id === selectedProfileId,
  );
  const selectedProfileRun = productDiscoveryRuns.find(
    (run) => run.territory_id === selectedProfileId,
  );
  const activeScreen = resolveActiveScreen(viewMode, selectedRunExists || Boolean(selectedProfileId));
  const currentRunContacts = selectedRunExists
    ? productContacts.filter((contact) => contact.campaign_id === selectedDiscoveryRunId)
    : profileBatch?.profile.id === selectedProfileId
      ? profileBatch.leads
      : [];
  const recentRunContacts = currentRunContacts.filter((contact) => isWithinLastSevenDays(contact.created_at));
  const fallbackWorkflowCounts: LeadWorkflowCounts = {
    inbox: currentRunContacts.filter((contact) => (contact.review_status || "unreviewed") === "unreviewed").length,
    this_week: recentRunContacts.length,
    shortlisted: currentRunContacts.filter((contact) => Boolean(contact.shortlisted_at)).length,
    contacted: currentRunContacts.filter((contact) => Boolean(contact.last_contacted_at || contact.latest_outcome)).length,
    dismissed: currentRunContacts.filter((contact) => contact.review_status === "not_fit" || Boolean(contact.contact_policy_status && contact.contact_policy_status !== "allowed")).length,
    all: currentRunContacts.length,
  };
  const workflowScopeId = selectedDiscoveryRunId
    || profileBatch?.audience_run_id
    || selectedProfileId;
  const workflowCounts = workflowSummary?.runId === workflowScopeId
    ? workflowSummary.counts
    : fallbackWorkflowCounts;
  const leadWorkflowItems: Array<{ id: LeadWorkflowView; label: string; count: number; icon: ReactNode }> = [
    {
      id: "inbox",
      label: "Leads",
      count: workflowCounts.inbox,
      icon: <List size={17} />,
    },
    {
      id: "shortlisted",
      label: "Shortlisted",
      count: workflowCounts.shortlisted,
      icon: <Star size={17} />,
    },
    {
      id: "contacted",
      label: "Contacted",
      count: workflowCounts.contacted,
      icon: <Send size={17} />,
    },
    {
      id: "dismissed",
      label: "Dismissed",
      count: workflowCounts.dismissed,
      icon: <CircleX size={17} />,
    },
  ];
  const visibleProfiles = useMemo(() => {
    if (workspaceExpanded || productProfiles.length <= 5) return productProfiles;
    const recent = productProfiles.slice(0, 5);
    const selected = productProfiles.find((item) => item.id === selectedProfileId);
    if (!selected || recent.some((item) => item === selected)) return recent;
    return [...recent.slice(0, 4), selected];
  }, [productProfiles, selectedProfileId, workspaceExpanded]);
  const handleWorkflowCountsChange = useCallback((runId: string, counts: LeadWorkflowCounts) => {
    setWorkflowSummary((current) => {
      if (current?.runId === runId && Object.keys(counts).every((key) => current.counts[key as LeadWorkflowView] === counts[key as LeadWorkflowView])) {
        return current;
      }
      return { runId, counts };
    });
  }, []);

  const availableResizableHeight = () =>
    Math.max(
      WORKFLOW_HEIGHT_MIN + MANAGE_HEIGHT_MIN,
      (railRef.current?.getBoundingClientRect().height || window.innerHeight) - RAIL_FIXED_HEIGHT_BUDGET,
    );

  const openWorkflowView = (nextView: LeadWorkflowView) => {
    setLeadWorkflowView(nextView);
    const targetRunId = selectedRunExists
      ? selectedDiscoveryRunId
      : selectedProfileRun?.id || (!selectedProfileId ? productDiscoveryRuns[0]?.id : undefined);
    if (targetRunId) {
      setSelectedDiscoveryRunId(targetRunId);
      void refreshSnapshot(targetRunId);
      selectScreen("results");
    }
    setMobileRailOpen(false);
  };

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
    window.history.pushState(null, "", "/app");
    setRoutePath("/app");
  };

  const startNewAudience = () => {
    if (isTraceRoute) returnToApp();
    setMobileRailOpen(false);
    setIsCreatingProduct(false);
    setViewMode("overview");
    setSelectedProfileId("");
    setSelectedDiscoveryRunId("");
  };

  const selectScreen = (screen: Screen) => {
    if (isTraceRoute) returnToApp();
    setViewMode(screen);
    setMobileRailOpen(false);
  };

  const selectProduct = (productId: string) => {
    setProductMenuOpen(false);
    setMobileRailOpen(false);
    if (productId === selectedProductId) return;

    setSelectedProductId(productId);
    const firstProfile = territories.find((profile) => profile.product_id === productId);
    setSelectedProfileId(firstProfile?.id || "");
    setSelectedDiscoveryRunId("");
    setLeadWorkflowView("inbox");
    setWorkflowSummary(null);
    setWorkspaceExpanded(false);
    setDraftRunNameState(readDraftRunName(productId));
    setViewMode("overview");
  };

  const handleDeleteSelectedProduct = async () => {
    if (!selectedProduct) return;
    await deleteProduct(selectedProduct.id);
    writeDraftRunName(selectedProduct.id, null);
    setDraftRunNameState(null);
    setSelectedDiscoveryRunId("");
    setViewMode("overview");
    showToast({ title: "Product deleted", message: `${selectedProductName} was removed.`, tone: "green" });
  };

  const handleRenameRun = async (runId: string, name: string) => {
    const existingNames = productRunLabels
      .filter((item) => item.run.id !== runId)
      .map((item) => item.title);
    await renameDiscoveryRun(runId, uniqueListName(name, existingNames));
    showToast({ title: "List renamed", tone: "green" });
  };

  const handleDeleteRun = async (run: DiscoveryRun) => {
    await deleteDiscoveryRuns([run.id]);
    if (selectedDiscoveryRunId === run.id) {
      setSelectedDiscoveryRunId("");
      setViewMode("overview");
    }
    showToast({ title: "Run deleted", message: "The saved contact list was removed.", tone: "green" });
  };

  const handleDeleteDraftRun = () => {
    setDraftRunName(null);
    setSelectedDiscoveryRunId("");
    setViewMode("overview");
  };

  const handleRenameAudience = async (profile: Territory, label: string) => {
    await renameProfile(profile.id, label);
    setRenameAudience(null);
    showToast({ title: "Audience renamed", tone: "green" });
  };

  const handleDeleteAudience = async (profile: Territory) => {
    const nextProfile = productProfiles.find((item) => item.id !== profile.id);
    await deleteProfile(profile.id);
    setDeleteAudience(null);
    if (selectedProfileId === profile.id) {
      setSelectedProfileId(nextProfile?.id || "");
      setSelectedDiscoveryRunId("");
      setViewMode("overview");
    }
    showToast({
      title: "Audience deleted",
      message: `${profile.label} was removed from this product.`,
      tone: "green",
    });
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
    setExportFileName(defaultExportFileName(selectedProductName));
    setExportDialogOpen(true);
  };

  const confirmExportProductContacts = () => {
    if (!productContacts.length) {
      setExportDialogOpen(false);
      showToast({
        title: "No contacts to export",
        message: "Run a search before exporting contacts for this product.",
        tone: "amber",
      });
      return;
    }
    if (!baseExportFileName(exportFileName)) {
      showToast({ title: "Name the export file", message: "Enter a filename before exporting.", tone: "amber" });
      return;
    }
    const downloadName = normalizeExportFileName(exportFileName);
    exportProductContactsCsv(productContacts, downloadName);
    setExportDialogOpen(false);
    showToast({
      title: "Contacts exported",
      message: `${productContacts.length} contacts downloaded as ${downloadName}.`,
      tone: "green",
    });
  };

  useEffect(() => {
    if (!error) return;
    showToast({ title: "Request failed", message: error, tone: "red" });
  }, [error, showToast]);

  useEffect(() => {
    const handlePopState = () => setRoutePath(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (!selectedProductId) {
      setDraftRunNameState(null);
      return;
    }
    setDraftRunNameState(readDraftRunName(selectedProductId));
  }, [selectedProductId]);

  useEffect(() => {
    if (!profileBatch || profileBatch.profile.id !== selectedProfileId) return;
    setViewMode("auto");
  }, [
    profileBatch?.audience_run_id,
    profileBatch?.outreach_campaign_id,
    profileBatch?.profile.id,
    selectedProfileId,
  ]);

  useEffect(() => {
    if (!productMenuOpen) return;

    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!productMenuRef.current?.contains(event.target as Node)) setProductMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setProductMenuOpen(false);
    };

    document.addEventListener("pointerdown", closeOnOutsideClick);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [productMenuOpen]);

  useEffect(() => {
    writeStoredDimension("scoutlead:rail-width", railWidth);
  }, [railWidth]);

  useEffect(() => {
    setWorkflowSectionHeight((current) =>
      Math.min(WORKFLOW_HEIGHT_MAX, Math.max(WORKFLOW_HEIGHT_MIN, current)),
    );
  }, []);

  useEffect(() => {
    writeStoredDimension("scoutlead:workflow-height", workflowSectionHeight);
  }, [workflowSectionHeight]);

  useEffect(() => {
    writeStoredDimension("scoutlead:manage-height", manageSectionHeight);
  }, [manageSectionHeight]);

  const railStyle = {
    "--rail-width": `${railWidth}px`,
    "--workflow-section-height": `${workflowSectionHeight}px`,
    "--manage-section-height": `${manageSectionHeight}px`,
  } as CSSProperties;

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
        <div className="mobile-brand">
          <span className="brand-mark">S</span>
          <strong>ScoutLead</strong>
        </div>
        <AccountControl accountSlot={accountSlot} placement="mobile" />
      </header>

      {mobileRailOpen ? (
        <button
          aria-label="Close menu"
          className="mobile-rail-backdrop"
          type="button"
          onClick={() => setMobileRailOpen(false)}
        />
      ) : null}

      <button
        aria-label={mobileRailOpen ? "Close menu" : "Open menu"}
        className="detail-rail-menu-button"
        type="button"
        onClick={() => setMobileRailOpen((open) => !open)}
      >
        <Menu size={18} />
      </button>

      <aside className="rail" ref={railRef} style={railStyle}>
        <div className="brand">
          <span className="brand-mark">S</span>
          <div className="brand-copy">
            <strong>ScoutLead</strong>
            <span>Discovery Console</span>
          </div>
        </div>

        <div
          className={productMenuOpen ? "rail-product-switcher is-open" : "rail-product-switcher"}
          ref={productMenuRef}
        >
          <button
            aria-expanded={productMenuOpen}
            aria-haspopup="menu"
            aria-label={`Current product: ${selectedProductName}`}
            className="rail-product-trigger"
            title={`Product: ${selectedProductName}`}
            type="button"
            onClick={() => setProductMenuOpen((open) => !open)}
          >
            <Package className="rail-product-icon" size={15} />
            <span className="rail-product-copy">
              <small>Product</small>
              <strong>{selectedProductName}</strong>
            </span>
            <ChevronDown className="rail-product-caret" size={14} />
          </button>

          {productMenuOpen ? (
            <div className="rail-product-menu" role="menu">
              <div className="rail-product-options">
                {products.map((product) => {
                  const active = product.id === selectedProductId;
                  return (
                    <button
                      aria-checked={active}
                      className={active ? "active" : ""}
                      key={product.id}
                      role="menuitemradio"
                      title={displayProductName(product)}
                      type="button"
                      onClick={() => selectProduct(product.id)}
                    >
                      <span>{displayProductName(product)}</span>
                      {active ? <Check size={13} /> : null}
                    </button>
                  );
                })}
                {!products.length ? <p>No products yet</p> : null}
              </div>
              <div className="rail-product-menu-actions">
                <button
                  role="menuitem"
                  type="button"
                  onClick={() => {
                    setProductMenuOpen(false);
                    setMobileRailOpen(false);
                    setIsCreatingProduct(true);
                  }}
                >
                  <Plus size={14} />
                  <span>New product</span>
                </button>
                <button
                  disabled={!selectedProduct}
                  role="menuitem"
                  type="button"
                  onClick={() => {
                    setProductMenuOpen(false);
                    selectScreen("product");
                  }}
                >
                  <Settings size={14} />
                  <span>Product settings</span>
                </button>
              </div>
            </div>
          ) : null}
        </div>

        <nav className="lead-workflow-nav" aria-label="Lead workflow">
          <div className="lead-workflow-links">
            {leadWorkflowItems.map((item) => (
              <button
                className={activeScreen === "results" && leadWorkflowView === item.id ? "active" : ""}
                key={item.id}
                aria-label={`${item.label}, ${item.count}`}
                title={`${item.label} (${item.count})`}
                type="button"
                onClick={() => openWorkflowView(item.id)}
              >
                {item.icon}
                <span>{item.label}</span>
                <em>{item.count}</em>
              </button>
            ))}
          </div>
          <ResizeHandle
            ariaLabel="Resize lead workflow section"
            axis="y"
            defaultValue={WORKFLOW_HEIGHT_DEFAULT}
            max={() =>
              Math.min(
                WORKFLOW_HEIGHT_MAX,
                Math.max(WORKFLOW_HEIGHT_MIN, availableResizableHeight() - manageSectionHeight),
              )
            }
            min={WORKFLOW_HEIGHT_MIN}
            onChange={setWorkflowSectionHeight}
            value={workflowSectionHeight}
          />
          <div className="lead-workspace-heading">
            <span>Audiences</span>
          </div>
          <div className="lead-workspace-list">
            {visibleProfiles.map((profile) => (
              <div className="audience-list-row" key={profile.id}>
                <button
                  className={`audience-list-main ${profile.id === selectedProfileId ? "active" : ""}`}
                  aria-label={profile.label}
                  title={profile.label}
                  type="button"
                  onClick={() => {
                    setLeadWorkflowView("inbox");
                    setMobileRailOpen(false);
                    void selectProfile(profile.id)
                      .then(() => setViewMode("auto"))
                      .catch((cause) => showToast({
                        title: "Audience could not be opened",
                        message: cause instanceof Error ? cause.message : String(cause),
                        tone: "red",
                      }));
                  }}
                >
                  {switchingProfileId === profile.id
                    ? <LoaderCircle className="lead-workspace-icon sl-spin-icon" size={15} />
                    : <Users className="lead-workspace-icon" size={15} />}
                  <span>{profile.label}</span>
                </button>
                <div className="audience-row-actions">
                  <button
                    aria-label={`Rename ${profile.label}`}
                    title="Rename audience"
                    type="button"
                    onClick={() => setRenameAudience(profile)}
                  >
                    <Pencil size={13} />
                  </button>
                  <button
                    aria-label={`Delete ${profile.label}`}
                    title="Delete audience"
                    type="button"
                    onClick={() => setDeleteAudience(profile)}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
            {productProfiles.length > 5 ? (
              <button
                className="workspace-more"
                type="button"
                onClick={() => setWorkspaceExpanded((expanded) => !expanded)}
              >
                <span>{workspaceExpanded ? "Show recent" : `View all (${productProfiles.length})`}</span>
              </button>
            ) : null}
            {!productProfiles.length ? (
              <p className="lead-workspace-empty">Create an audience to start receiving leads.</p>
            ) : null}
          </div>
        </nav>

        <ResizeHandle
          ariaLabel="Resize Manage section"
          axis="y"
          className="manage-section-resizer"
          defaultValue={MANAGE_HEIGHT_DEFAULT}
          direction={-1}
          max={() => Math.max(MANAGE_HEIGHT_MIN, availableResizableHeight() - workflowSectionHeight)}
          min={MANAGE_HEIGHT_MIN}
          onChange={setManageSectionHeight}
          value={manageSectionHeight}
        />
        <ProductManagementSection
          activeScreen={activeScreen}
          integrationCount={getEnabledIntegrationCount(selectedProduct, Boolean(gmailConnectionStatus?.connected))}
          hasProduct={Boolean(selectedProduct)}
          hasContacts={productContacts.length > 0}
          onExport={handleExportProductContacts}
          onIntegrations={() => selectScreen("integrations")}
          onProductSettings={() => selectScreen("product")}
        />
        <div className="rail-account-footer">
          <AccountControl accountSlot={accountSlot} placement="desktop" />
          <span className="rail-account-label">Account</span>
        </div>
        <ResizeHandle
          ariaLabel="Resize navigation width"
          axis="x"
          className="rail-width-resizer"
          defaultValue={RAIL_WIDTH_DEFAULT}
          max={RAIL_WIDTH_MAX}
          min={RAIL_WIDTH_MIN}
          onChange={setRailWidth}
          value={railWidth}
        />
      </aside>

      <section
        className={["product", "integrations"].includes(activeScreen) ? "main main-settings-screen" : "main"}
      >
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
              {
                isCreatingProduct: false,
                onCreatingProductChange: setIsCreatingProduct,
                onDeleteProduct: handleDeleteSelectedProduct,
              },
              {
                draftRunName: draftRunName ?? undefined,
                onRunCreated: (run) => {
                  writeDraftRunName(run.product_id, null);
                  if (run.product_id === selectedProductId) setDraftRunNameState(null);
                  setSelectedDiscoveryRunId(run.id);
                  setViewMode("auto");
                },
              },
              {
                view: leadWorkflowView,
                onViewChange: setLeadWorkflowView,
                onCountsChange: handleWorkflowCountsChange,
                onCreateAudience: startNewAudience,
              },
              {
                onCountChange: (runId, count) => setSourceReviewSummary({ runId, count }),
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
            const created = await createProductFromProfile(input);
            if (created) {
              setSelectedProductId(created.id);
              setSelectedDiscoveryRunId("");
              setViewMode("product");
            }
            return created;
          }}
        />
      ) : null}
      {exportDialogOpen ? (
        <ExportContactsDialog
          contactCount={productContacts.length}
          fileName={exportFileName}
          placeholder={defaultExportFileName(selectedProductName)}
          previewFileName={
            baseExportFileName(exportFileName) ? normalizeExportFileName(exportFileName) : "filename.csv"
          }
          onChange={setExportFileName}
          onClose={() => setExportDialogOpen(false)}
          onExport={confirmExportProductContacts}
        />
      ) : null}
      {renameAudience ? (
        <RenameAudienceDialog
          audience={renameAudience}
          onClose={() => setRenameAudience(null)}
          onRename={handleRenameAudience}
        />
      ) : null}
      {deleteAudience ? (
        <DeleteAudienceDialog
          audience={deleteAudience}
          onClose={() => setDeleteAudience(null)}
          onDelete={handleDeleteAudience}
        />
      ) : null}
    </div>
  );
}

function ResizeHandle({
  ariaLabel,
  axis,
  className = "",
  defaultValue,
  direction = 1,
  max,
  min,
  onChange,
  value,
}: {
  ariaLabel: string;
  axis: "x" | "y";
  className?: string;
  defaultValue: number;
  direction?: 1 | -1;
  max: number | (() => number);
  min: number;
  onChange: (value: number) => void;
  value: number;
}) {
  const dragStart = useRef<{ coordinate: number; value: number } | null>(null);
  const resolvedMax = () => Math.max(min, typeof max === "function" ? max() : max);
  const updateValue = (nextValue: number) => {
    onChange(Math.round(Math.min(resolvedMax(), Math.max(min, nextValue))));
  };
  const coordinate = (event: ReactPointerEvent<HTMLDivElement>) =>
    axis === "x" ? event.clientX : event.clientY;

  const startDragging = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragStart.current = { coordinate: coordinate(event), value };
    document.body.classList.add("is-resizing-navigation");
  };

  const stopDragging = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragStart.current = null;
    document.body.classList.remove("is-resizing-navigation");
  };

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const decrementKey = axis === "x" ? "ArrowLeft" : "ArrowUp";
    const incrementKey = axis === "x" ? "ArrowRight" : "ArrowDown";
    if (![decrementKey, incrementKey, "Home"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Home") {
      updateValue(defaultValue);
      return;
    }
    const physicalDelta = event.key === incrementKey ? 1 : -1;
    updateValue(value + physicalDelta * direction * (event.shiftKey ? 24 : 8));
  };

  return (
    <div
      aria-label={ariaLabel}
      aria-orientation={axis === "x" ? "vertical" : "horizontal"}
      aria-valuemax={resolvedMax()}
      aria-valuemin={min}
      aria-valuenow={value}
      className={["navigation-resizer", axis === "x" ? "is-vertical" : "is-horizontal", className]
        .filter(Boolean)
        .join(" ")}
      role="separator"
      tabIndex={0}
      title={`${ariaLabel}. Double-click to reset.`}
      onDoubleClick={() => updateValue(defaultValue)}
      onKeyDown={handleKeyDown}
      onLostPointerCapture={() => {
        dragStart.current = null;
        document.body.classList.remove("is-resizing-navigation");
      }}
      onPointerDown={startDragging}
      onPointerMove={(event) => {
        if (!dragStart.current) return;
        const delta = (coordinate(event) - dragStart.current.coordinate) * direction;
        updateValue(dragStart.current.value + delta);
      }}
      onPointerUp={stopDragging}
    />
  );
}

function AccountControl({ accountSlot, placement }: { accountSlot?: ReactNode; placement: "desktop" | "mobile" }) {
  if (accountSlot) {
    return <div className={placement === "mobile" ? "mobile-avatar-auth" : "top-avatar-auth"}>{accountSlot}</div>;
  }

  if (placement === "mobile") {
    return (
      <button aria-label="Account" className="mobile-icon-button mobile-avatar-button" type="button">
        <User size={17} />
      </button>
    );
  }

  return (
    <button className="top-avatar" type="button" aria-label="Account">
      <User size={16} />
    </button>
  );
}

function ProductManagementSection({
  activeScreen,
  hasContacts,
  hasProduct,
  integrationCount,
  onExport,
  onIntegrations,
  onProductSettings,
}: {
  activeScreen: Screen;
  hasContacts: boolean;
  hasProduct: boolean;
  integrationCount: number;
  onExport: () => void;
  onIntegrations: () => void;
  onProductSettings: () => void;
}) {
  return (
    <section className="mng" aria-label="Product management">
      <p className="mng-label">Manage</p>
      <button
        className={manageItemClass(hasProduct, activeScreen === "product")}
        disabled={!hasProduct}
        aria-label="Product settings"
        title="Product settings"
        type="button"
        onClick={onProductSettings}
      >
        <span className="mng-icon">
          <Settings size={13} />
        </span>
        <span className="mng-label-text">Product settings</span>
      </button>
      <button
        className={manageItemClass(hasProduct, activeScreen === "integrations")}
        disabled={!hasProduct}
        aria-label="Integrations"
        title="Integrations"
        type="button"
        onClick={onIntegrations}
      >
        <span className="mng-icon">
          <Plug size={13} />
        </span>
        <span className="mng-label-text">Integrations</span>
        {integrationCount > 0 ? <span className="mng-badge">{integrationCount} on</span> : null}
      </button>
      <button
        className={hasContacts ? "mng-item" : "mng-item is-disabled"}
        disabled={!hasContacts}
        aria-label="Export all contacts"
        title="Export all contacts"
        type="button"
        onClick={onExport}
      >
        <span className="mng-icon">
          <Download size={13} />
        </span>
        <span className="mng-label-text">Export all contacts</span>
      </button>
    </section>
  );
}

function manageItemClass(enabled: boolean, active: boolean) {
  return [enabled ? "mng-item" : "mng-item is-disabled", active ? "is-active" : ""].filter(Boolean).join(" ");
}

function resolveActiveScreen(
  viewMode: AppViewMode,
  hasSelectedRun: boolean,
): Screen {
  if (viewMode === "product" || viewMode === "integrations") return viewMode;
  if (viewMode !== "auto") return viewMode;
  return hasSelectedRun ? "results" : "overview";
}

function RunHistoryDraft({
  active,
  existingNames,
  value,
  onChange,
  onSelect,
  onDelete,
}: {
  active: boolean;
  existingNames: string[];
  value: string;
  onChange: (value: string) => void;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const displayName = value.trim() || "New search";

  useEffect(() => {
    if (!active) setEditing(false);
  }, [active]);

  const commitName = () => {
    onChange(uniqueListName(displayName, existingNames));
    setEditing(false);
  };

  const confirmDelete = () => {
    setConfirmingDelete(false);
    setEditing(false);
    onDelete();
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
      {confirmingDelete ? (
        <div className="run-confirm">
          <span className="q">Delete draft?</span>
          <button className="yes" type="button" onClick={confirmDelete}>
            Delete
          </button>
          <button type="button" onClick={() => setConfirmingDelete(false)}>
            Cancel
          </button>
        </div>
      ) : null}
      <div className="list-row-actions run-actions">
        <button
          aria-label={`Rename ${displayName}`}
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
          aria-label={`Delete ${displayName}`}
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

function RunHistoryItem({
  active,
  run,
  title,
  contacts,
  territory,
  onDelete,
  onRename,
  onSelect,
}: {
  active: boolean;
  run: DiscoveryRun;
  title: string;
  contacts: DiscoveryResult[];
  territory?: Territory;
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
            {territory?.unviewed_delivery_count ? (
              <span className="run-new-badge">New {territory.unviewed_delivery_count}</span>
            ) : null}
            <span className="run-yield">
              {territory?.last_run_at
                ? `${territory.last_delivery_count} delivered`
                : runYield(run, contacts)}
            </span>
            <span className={territory?.status === "paused" ? "run-status is-paused" : "run-status"}>
              {territory ? (
                <><CalendarClock size={10} /> {territory.status === "active" ? "weekly" : "paused"}</>
              ) : listMeta(run)}
            </span>
            <span className="run-when">
              {territory?.next_run_at ? formatScheduleDate(territory.next_run_at) : formatRunDate(run.created_at)}
            </span>
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
      {!territory ? <div className="list-row-actions run-actions">
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
      </div> : null}
    </div>
  );
}

function RenameAudienceDialog({
  audience,
  onClose,
  onRename,
}: {
  audience: Territory;
  onClose: () => void;
  onRename: (audience: Territory, label: string) => Promise<void>;
}) {
  const [label, setLabel] = useState(audience.label);
  const [saving, setSaving] = useState(false);
  const cleanedLabel = label.trim();

  return (
    <Modal title="Rename audience" onClose={onClose}>
      <form
        className="audience-dialog-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!cleanedLabel || cleanedLabel === audience.label || saving) return;
          setSaving(true);
          try {
            await onRename(audience, cleanedLabel);
          } finally {
            setSaving(false);
          }
        }}
      >
        <label className="field">
          <span>Audience name</span>
          <input
            autoFocus
            maxLength={255}
            value={label}
            onChange={(event) => setLabel(event.target.value)}
          />
        </label>
        <div className="dialog-actions">
          <button className="secondary" type="button" onClick={onClose}>Cancel</button>
          <button
            className="runbtn"
            disabled={!cleanedLabel || cleanedLabel === audience.label || saving}
            type="submit"
          >
            {saving ? "Saving..." : "Save name"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteAudienceDialog({
  audience,
  onClose,
  onDelete,
}: {
  audience: Territory;
  onClose: () => void;
  onDelete: (audience: Territory) => Promise<void>;
}) {
  const [deleting, setDeleting] = useState(false);
  return (
    <Modal title="Delete audience" onClose={onClose}>
      <div className="audience-delete-dialog">
        <p>
          Remove <strong>{audience.label}</strong> from this product? Existing lead history will be retained.
        </p>
        <div className="dialog-actions">
          <button className="secondary" type="button" onClick={onClose}>Cancel</button>
          <button
            className="danger"
            disabled={deleting}
            type="button"
            onClick={async () => {
              if (deleting) return;
              setDeleting(true);
              try {
                await onDelete(audience);
              } finally {
                setDeleting(false);
              }
            }}
          >
            <Trash2 size={14} />
            {deleting ? "Deleting..." : "Delete audience"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function AddProductDialog({
  products,
  onClose,
  onCreate,
}: {
  products: Product[];
  onClose: () => void;
  onCreate: (input: ProductProfileInput) => Promise<Product | null>;
}) {
  const { showToast } = useToast();
  const [productName, setProductName] = useState("");
  const [offerSummary, setOfferSummary] = useState("");
  const [targetCustomer, setTargetCustomer] = useState("");
  const [problemBeingSolved, setProblemBeingSolved] = useState("");
  const [opportunitySignals, setOpportunitySignals] = useState("");
  const [exclusions, setExclusions] = useState("");
  const [creating, setCreating] = useState(false);
  const [localError, setLocalError] = useState("");
  const normalizedProductName = productName.trim().toLowerCase();
  const hasDuplicateProductName =
    normalizedProductName.length > 0 &&
    products.some((product) => product.product_name.trim().toLowerCase() === normalizedProductName);
  const canCreateProduct =
    productName.trim().length > 0 &&
    offerSummary.trim().length > 0 &&
    targetCustomer.trim().length > 0 &&
    problemBeingSolved.trim().length > 0 &&
    !hasDuplicateProductName &&
    !creating;

  const submit = async () => {
    if (!canCreateProduct) return;
    setCreating(true);
    setLocalError("");
    try {
      const created = await onCreate({
        product_name: productName.trim(),
        offer_summary: offerSummary.trim(),
        target_customer: targetCustomer.trim(),
        problem_being_solved: problemBeingSolved.trim(),
        ideal_customer_signals: parseProfileValues(opportunitySignals),
        exclusions: parseProfileValues(exclusions),
      });
      if (!created) {
        showToast({ title: "Product was not created", message: "Check the product details and try again.", tone: "red" });
        return;
      }
      showToast({
        title: "Product created",
        message: "The product profile is ready for its first search.",
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
    <Modal className="add-product-modal" title="New product" onClose={onClose}>
      <form
        className="add-product-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="add-product-fields">
          <label className="field add-product-name-field">
            <span>Product name</span>
            <input
              autoFocus
              placeholder="Local Service Website Growth"
              value={productName}
              onChange={(event) => setProductName(event.target.value)}
            />
            {hasDuplicateProductName ? <em>A product with this name already exists.</em> : null}
          </label>
          <label className="field add-product-offer-field">
            <span>What you sell</span>
            <textarea
              placeholder="Website and conversion improvements for local businesses."
              rows={3}
              value={offerSummary}
              onChange={(event) => setOfferSummary(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Ideal customer</span>
            <textarea
              placeholder="Independent home-service businesses."
              rows={3}
              value={targetCustomer}
              onChange={(event) => setTargetCustomer(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Problem solved</span>
            <textarea
              placeholder="Weak websites and missing quote or booking flows."
              rows={3}
              value={problemBeingSolved}
              onChange={(event) => setProblemBeingSolved(event.target.value)}
            />
          </label>
        </div>
        <details className="add-product-advanced">
          <summary>
            <span>Advanced criteria</span>
            <ChevronDown size={15} />
          </summary>
          <div className="add-product-advanced-fields">
            <label className="field">
              <span>Opportunity signals</span>
              <textarea
                placeholder="Active business, weak conversion flow, low review count"
                rows={3}
                value={opportunitySignals}
                onChange={(event) => setOpportunitySignals(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Exclude</span>
              <textarea
                placeholder="Agencies, directories, national chains"
                rows={3}
                value={exclusions}
                onChange={(event) => setExclusions(event.target.value)}
              />
            </label>
          </div>
        </details>
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

function parseProfileValues(value: string) {
  return [...new Set(
    value
      .split(/[\n,;]+/)
      .map((item) => item.trim())
      .filter(Boolean),
  )];
}

function displayProductName(product: Product) {
  const savedName = product.product_name.trim();
  if (savedName && !/^(new product|untitled product|product)$/i.test(savedName)) return savedName;
  const text = (product.offer_summary || product.product_description || "").trim();
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
  if (run.name && !isGeneratedRunName(run.name) && !isPlaceholderRunName(run.name)) return run.name;
  const intent = run.source_inputs?.source_request_intent;
  if (isRecord(intent)) {
    const category = typeof intent.business_category === "string" ? intent.business_category.trim() : "";
    const location = typeof intent.location === "string" ? intent.location.trim() : "";
    if (category && location) return `${titleCase(category)} · ${titleCase(location)}`;
    if (category) return titleCase(category);
  }
  const prompt = getRunPrompt(run);
  if (prompt) return titleFromQuery(prompt) || prompt;
  if (run.name && !isPlaceholderRunName(run.name)) return run.name;
  return "Untitled search";
}

function groupedRunLabels(runs: DiscoveryRun[], territories: Territory[]) {
  const territoryById = new Map(territories.map((territory) => [territory.id, territory]));
  const groupedIds = new Set<string>();
  const labels: Array<{
    run: DiscoveryRun;
    runIds: string[];
    territory?: Territory;
    title: string;
  }> = [];
  const usedNames: string[] = [];

  for (const run of runs) {
    const territory = run.territory_id ? territoryById.get(run.territory_id) : undefined;
    if (territory) {
      if (groupedIds.has(territory.id)) continue;
      groupedIds.add(territory.id);
      const territoryRuns = runs.filter((candidate) => candidate.territory_id === territory.id);
      const title = uniqueListName(territory.label, usedNames);
      usedNames.push(title);
      labels.push({ run: territoryRuns[0] || run, runIds: territoryRuns.map((candidate) => candidate.id), territory, title });
      continue;
    }
    const title = uniqueListName(listLabel(run), usedNames);
    usedNames.push(title);
    labels.push({ run, runIds: [run.id], title });
  }
  return labels;
}

function uniqueListName(requestedName: string, existingNames: string[]) {
  const baseName = collapseListName(requestedName) || "Untitled list";
  const existing = new Set(existingNames.map(nameKey).filter(Boolean));
  if (!existing.has(nameKey(baseName))) return baseName;

  let suffix = 1;
  while (true) {
    const candidate = `${baseName} ${suffix}`;
    if (!existing.has(nameKey(candidate))) return candidate;
    suffix += 1;
  }
}

function nameKey(value: string) {
  return collapseListName(value).toLowerCase();
}

function collapseListName(value: string) {
  return value.trim().replace(/\s+/g, " ");
}

function isGeneratedRunName(value: string) {
  return /\b(source request|discovery|validation)\b.*\d{4}-\d{2}-\d{2}/i.test(value);
}

function isPlaceholderRunName(value: string) {
  return /^(?:page name|test|new test\s*\d*|new search(?:\s+\d+)?)$/i.test(collapseListName(value));
}

function listMeta(run: DiscoveryRun) {
  const status = run.status.replace(/_/g, " ");
  return status;
}

function runDotClass(run: DiscoveryRun) {
  const status = run.status.toLowerCase();
  if (
    ["expanding", "discovering", "researching", "qualifying", "drafting_outreach", "sending"].includes(
      status,
    )
  ) {
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

function formatScheduleDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "weekly";
  return `next ${date.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
}

function draftRunStorageKey(productId: string) {
  return `draftDiscoveryRunName:${productId}`;
}

function readDraftRunName(productId: string) {
  if (!productId) return null;
  const savedName = localStorage.getItem(draftRunStorageKey(productId));
  return savedName && isPlaceholderRunName(savedName) ? "New search" : savedName;
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

function readStoredDimension(key: string, fallback: number, min: number, max: number) {
  try {
    const stored = Number.parseInt(localStorage.getItem(key) || "", 10);
    return Number.isFinite(stored) ? Math.min(max, Math.max(min, stored)) : fallback;
  } catch {
    return fallback;
  }
}

function writeStoredDimension(key: string, value: number) {
  try {
    localStorage.setItem(key, String(Math.round(value)));
  } catch {
    // Resizing remains available when browser storage is disabled.
  }
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

function exportProductContactsCsv(contacts: DiscoveryResult[], fileName: string) {
  const rows = contacts.map((contact) => ({
    company: contact.company_name,
    contact_name: contact.research?.contact_name || "",
    email: exportContactEmail(contact.contact_email || contact.research?.contact_email),
    phone: rawContactValue(contact, ["phone", "telephone", "contact_phone", "phoneNumber"]),
    website: contact.website_url || contact.research?.website_url || "",
    geography: contact.geography || contact.research?.geography || "",
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
  anchor.download = normalizeExportFileName(fileName);
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

function getEnabledIntegrationCount(product: Product | undefined, gmailConnected: boolean) {
  return Number(gmailConnected) + Number(Boolean(product?.webhook_enabled && product.webhook_url));
}

function isWithinLastSevenDays(value: string) {
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) && timestamp >= Date.now() - 7 * 24 * 60 * 60 * 1000;
}

function csvCell(value: string | number | undefined) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}
