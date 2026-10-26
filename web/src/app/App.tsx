import {
  ArrowRight,
  ChevronDown,
  CircleX,
  Download,
  Folder,
  FolderOpen,
  ChartPie,
  List,
  LoaderCircle,
  Menu,
  MoreVertical,
  Pencil,
  PlayCircle,
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
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { renderScreen } from "../routes/screen-router";
import { TraceDebugScreen } from "../screens/TraceDebugScreen";
import { ExportContactsDialog, Modal, ToastProvider, useToast } from "../shared-ui";
import { AppDataProvider, useAppData } from "../state/app-data";
import type {
  AudienceFolder,
  Product,
  ProductProfileInput,
  Territory,
} from "../types/domain";
import type { LeadWorkflowCounts, LeadWorkflowView, Screen } from "../types/navigation";
import {
  baseExportFileName,
  defaultExportFileName,
  exportContactsCsv,
  normalizeExportFileName,
} from "../utils/export-file";
import { formatDate } from "../utils/format";

type AppProps = {
  getAuthToken?: () => Promise<string | null>;
  accountSlot?: ReactNode;
  accountId?: string;
  approverLabel?: string;
};

type AppViewMode = "auto" | Screen;

const RAIL_WIDTH_DEFAULT = 244;
const RAIL_WIDTH_MIN = 220;
const RAIL_WIDTH_MAX = 420;
const WORKFLOW_HEIGHT_DEFAULT = 230;
const WORKFLOW_HEIGHT_MIN = 220;
const WORKFLOW_HEIGHT_MAX = 260;
const MANAGE_HEIGHT_DEFAULT = 151;
const MANAGE_HEIGHT_MIN = 112;
const RAIL_FIXED_HEIGHT_BUDGET = 330;

export function App({ getAuthToken, accountSlot, accountId, approverLabel }: AppProps = {}) {
  return (
    <ToastProvider>
      <AppDataProvider getAuthToken={getAuthToken} approverLabel={approverLabel}>
        <AppShell accountId={accountId} accountName={approverLabel} accountSlot={accountSlot} />
      </AppDataProvider>
    </ToastProvider>
  );
}

function AppShell({
  accountId,
  accountName,
  accountSlot,
}: {
  accountId?: string;
  accountName?: string;
  accountSlot?: ReactNode;
}) {
  const navigationStorageKey = `scoutlead:last-view:${accountId || "local"}`;
  const workflowStorageKey = `scoutlead:last-workflow:${accountId || "local"}`;
  const [viewMode, setViewMode] = useState<AppViewMode>(() => readStoredAppView(navigationStorageKey));
  const [leadWorkflowView, setLeadWorkflowView] = useState<LeadWorkflowView>(() =>
    readStoredWorkflowView(workflowStorageKey),
  );
  const [leadListRequestId, setLeadListRequestId] = useState(0);
  const [isCreatingProduct, setIsCreatingProduct] = useState(false);
  const [renameAudience, setRenameAudience] = useState<Territory | null>(null);
  const [deleteAudience, setDeleteAudience] = useState<Territory | null>(null);
  const [editFolder, setEditFolder] = useState<AudienceFolder | "new" | null>(null);
  const [deleteFolder, setDeleteFolder] = useState<AudienceFolder | null>(null);
  const [moveAudience, setMoveAudience] = useState<Territory | null>(null);
  const [newAudienceFolderId, setNewAudienceFolderId] = useState("");
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({});
  const [audienceMenuId, setAudienceMenuId] = useState("");
  const [folderMenuId, setFolderMenuId] = useState("");
  const [mobileRailOpen, setMobileRailOpen] = useState(false);
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
  const railRef = useRef<HTMLElement | null>(null);
  const { showToast } = useToast();
  const onboardingStorageKey = `scoutlead:product-onboarding:${accountId || "local"}`;
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
    audienceFolders,
    gmailConnectionStatus,
    createProductFromProfile,
    renameProfile,
    deleteProfile,
    createAudienceFolder,
    renameAudienceFolder,
    deleteAudienceFolder,
    updateProfile,
  } = useAppData();
  const selectedProduct = products.find((product) => product.id === selectedProductId);
  const selectedProductName = selectedProduct ? displayProductName(selectedProduct) : "No product";
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
  const activeScreen = resolveActiveScreen(viewMode, selectedRunExists || Boolean(selectedProfileId));
  const recentProductContacts = productContacts.filter((contact) => isWithinLastSevenDays(contact.created_at));
  const workflowCounts: LeadWorkflowCounts = {
    inbox: productContacts.length,
    this_week: recentProductContacts.length,
    shortlisted: productContacts.filter((contact) => Boolean(contact.shortlisted_at)).length,
    contacted: productContacts.filter((contact) => Boolean(contact.last_contacted_at || contact.latest_outcome)).length,
    dismissed: productContacts.filter((contact) => contact.review_status === "not_fit" || Boolean(contact.contact_policy_status && contact.contact_policy_status !== "allowed")).length,
    all: productContacts.length,
  };
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
  const unfiledProfiles = useMemo(() => {
    const profiles = productProfiles.filter((profile) => !profile.folder_id);
    if (profiles.length <= 5) return profiles;
    const recent = profiles.slice(0, 5);
    const selected = profiles.find((profile) => profile.id === selectedProfileId);
    if (!selected || recent.some((profile) => profile.id === selected.id)) return recent;
    return [...recent.slice(0, 4), selected];
  }, [productProfiles, selectedProfileId]);
  const availableResizableHeight = () =>
    Math.max(
      WORKFLOW_HEIGHT_MIN + MANAGE_HEIGHT_MIN,
      (railRef.current?.getBoundingClientRect().height || window.innerHeight) - RAIL_FIXED_HEIGHT_BUDGET,
    );

  const openWorkflowView = (nextView: LeadWorkflowView) => {
    setLeadWorkflowView(nextView);
    setLeadListRequestId((requestId) => requestId + 1);
    setSelectedProfileId("");
    setSelectedDiscoveryRunId("");
    selectScreen("results");
    setMobileRailOpen(false);
  };

  const openAudienceOverview = () => {
    setSelectedProfileId("");
    setSelectedDiscoveryRunId("");
    setViewMode("audiences");
    setMobileRailOpen(false);
  };

  const openAudienceProfile = (profile: Territory) => {
    setAudienceMenuId("");
    setFolderMenuId("");
    setLeadWorkflowView("inbox");
    setMobileRailOpen(false);
    void selectProfile(profile.id)
      .then(() => setViewMode("auto"))
      .catch((cause) => showToast({
        title: "Audience could not be opened",
        message: cause instanceof Error ? cause.message : String(cause),
        tone: "red",
      }));
  };

  const returnToApp = () => {
    window.history.pushState(null, "", "/app");
    setRoutePath("/app");
  };

  const startNewAudience = (folderId = "") => {
    if (isTraceRoute) returnToApp();
    setMobileRailOpen(false);
    setIsCreatingProduct(false);
    setViewMode("overview");
    setSelectedProfileId("");
    setSelectedDiscoveryRunId("");
    setAudienceMenuId("");
    setFolderMenuId("");
    setNewAudienceFolderId(folderId);
  };

  const selectScreen = (screen: Screen) => {
    if (isTraceRoute) returnToApp();
    setViewMode(screen);
    setMobileRailOpen(false);
  };

  const handleRenameAudience = async (profile: Territory, label: string) => {
    await renameProfile(profile.id, label);
    setRenameAudience(null);
    showToast({ title: "Audience renamed", tone: "green" });
  };

  const handleDeleteAudience = async (profile: Territory) => {
    await deleteProfile(profile.id);
    setDeleteAudience(null);
    if (selectedProfileId === profile.id) {
      setSelectedProfileId("");
      setSelectedDiscoveryRunId("");
      setViewMode("audiences");
    }
    showToast({
      title: "Audience deleted",
      message: `${profile.label} was removed.`,
      tone: "green",
    });
  };

  const handleExportProductContacts = () => {
    if (!productContacts.length) {
      showToast({
        title: "No contacts to export",
        message: "Run a search before exporting contacts.",
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
        message: "Run a search before exporting contacts.",
        tone: "amber",
      });
      return;
    }
    if (!baseExportFileName(exportFileName)) {
      showToast({ title: "Name the export file", message: "Enter a filename before exporting.", tone: "amber" });
      return;
    }
    const downloadName = normalizeExportFileName(exportFileName);
    exportContactsCsv(productContacts, downloadName);
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
    if (loading || products.length || localStorage.getItem(onboardingStorageKey) === "dismissed") return;
    setIsCreatingProduct(true);
  }, [loading, onboardingStorageKey, products.length]);

  useEffect(() => {
    if (!profileBatch || profileBatch.audience.id !== selectedProfileId) return;
    setViewMode("auto");
  }, [
    profileBatch?.audience_run_id,
    profileBatch?.outreach_campaign_id,
    profileBatch?.audience.id,
    selectedProfileId,
  ]);

  useEffect(() => {
    writeStoredValue(navigationStorageKey, viewMode === "overview" ? "audiences" : viewMode);
  }, [navigationStorageKey, viewMode]);

  useEffect(() => {
    writeStoredValue(workflowStorageKey, leadWorkflowView);
  }, [leadWorkflowView, workflowStorageKey]);

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

        <button className="rail-new-audience" type="button" onClick={() => startNewAudience()}>
          <Plus size={16} />
          <span>New audience</span>
        </button>

        <nav className="lead-workflow-nav" aria-label="Lead workflow">
          <div className="lead-workflow-links">
            <button
              className={activeScreen === "audiences" ? "active" : ""}
              aria-label={`Overview, ${productProfiles.length} audiences`}
              title={`Overview (${productProfiles.length} audiences)`}
              type="button"
              onClick={openAudienceOverview}
            >
              <ChartPie size={17} />
              <span>Overview</span>
              <em>{productProfiles.length}</em>
            </button>
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
            <button className="audience-new-folder" aria-label="New folder" title="New folder" type="button" onClick={() => setEditFolder("new")}><Plus size={15} /></button>
          </div>
          <div className="lead-workspace-list">
            <>
                {audienceFolders.map((folder) => {
                  const profiles = productProfiles.filter((profile) => profile.folder_id === folder.id);
                  const open = expandedFolders[folder.id] || profiles.some((profile) => profile.id === selectedProfileId);
                  return <section className="audience-folder" key={folder.id}>
                    <div className="audience-folder-row">
                      <button aria-expanded={open} className="audience-folder-main" type="button" onClick={() => setExpandedFolders((current) => ({ ...current, [folder.id]: !open }))}>
                        {open ? <FolderOpen size={15} /> : <Folder size={15} />}<span>{folder.name}</span><em>{profiles.length}</em>
                      </button>
                      <div className="audience-folder-actions"><button aria-expanded={folderMenuId === folder.id} aria-label={`Actions for ${folder.name}`} type="button" onClick={() => { setAudienceMenuId(""); setFolderMenuId((current) => current === folder.id ? "" : folder.id); }}><MoreVertical size={15} /></button>{folderMenuId === folder.id ? <div className="audience-sidebar-menu"><button type="button" onClick={() => { setFolderMenuId(""); startNewAudience(folder.id); }}><Plus size={13} />New</button><button type="button" onClick={() => { setFolderMenuId(""); setEditFolder(folder); }}><Pencil size={13} />Rename</button><button className="is-danger" type="button" onClick={() => { setFolderMenuId(""); setDeleteFolder(folder); }}><Trash2 size={13} />Delete</button></div> : null}</div>
                    </div>
                    {open ? <div className="audience-folder-children">{profiles.length ? profiles.map((profile) => <AudienceSidebarRow key={profile.id} menuOpen={audienceMenuId === profile.id} profile={profile} selected={profile.id === selectedProfileId} switching={switchingProfileId === profile.id} onDelete={() => { setAudienceMenuId(""); setDeleteAudience(profile); }} onMenuToggle={() => { setFolderMenuId(""); setAudienceMenuId((current) => current === profile.id ? "" : profile.id); }} onMove={() => { setAudienceMenuId(""); setMoveAudience(profile); }} onOpen={() => openAudienceProfile(profile)} onRename={() => { setAudienceMenuId(""); setRenameAudience(profile); }} />) : <small className="audience-folder-empty">No audiences</small>}</div> : null}
                  </section>;
                })}
                {productProfiles.some((profile) => !profile.folder_id) ? <div className="audience-recents-heading"><span>Recents</span><em>{productProfiles.filter((profile) => !profile.folder_id).length}</em></div> : null}
                {unfiledProfiles.map((profile) => <AudienceSidebarRow key={profile.id} menuOpen={audienceMenuId === profile.id} profile={profile} selected={profile.id === selectedProfileId} switching={switchingProfileId === profile.id} onDelete={() => { setAudienceMenuId(""); setDeleteAudience(profile); }} onMenuToggle={() => { setFolderMenuId(""); setAudienceMenuId((current) => current === profile.id ? "" : profile.id); }} onMove={() => { setAudienceMenuId(""); setMoveAudience(profile); }} onOpen={() => openAudienceProfile(profile)} onRename={() => { setAudienceMenuId(""); setRenameAudience(profile); }} />)}
            </>
            {productProfiles.length > 5 ? (
              <button
                className="workspace-more"
                type="button"
                onClick={openAudienceOverview}
              >
                <span>{`View all (${productProfiles.length})`}</span>
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
        {activeScreen !== "results" ? (
          <header className={activeScreen === "product" ? "desktop-account-bar has-summary" : "desktop-account-bar"}>
            {activeScreen === "overview" || activeScreen === "audiences" ? (
              activeScreen === "audiences" ? (
                <div className="desktop-overview-context">
                  <span>Account-wide performance</span>
                  <strong>Overview</strong>
                </div>
              ) : (
                <nav aria-label="Audience context" className="results-breadcrumb desktop-audience-context">
                  <span>Audiences</span>
                  <span aria-hidden="true">/</span>
                  <strong>New audience</strong>
                </nav>
              )
            ) : null}
            {activeScreen === "integrations" || activeScreen === "product" ? (
              <div className="desktop-settings-context">
                <nav aria-label="Page context" className="results-breadcrumb">
                  <span>Manage</span>
                  <span aria-hidden="true">/</span>
                  <strong>{activeScreen === "integrations" ? "Integrations" : "Settings"}</strong>
                </nav>
                {activeScreen === "product" && selectedProduct ? (
                  <div className="desktop-settings-stats" aria-label="Account summary">
                    <span><b>{productDiscoveryRuns.length}</b> {productDiscoveryRuns.length === 1 ? "run" : "runs"}</span>
                    <span><b>{productContacts.length}</b> {productContacts.length === 1 ? "contact" : "contacts"}</span>
                    <span>updated <b>{formatDate(selectedProduct.updated_at)}</b></span>
                  </div>
                ) : null}
              </div>
            ) : null}
            {accountName ? <span title={accountName}>{accountName}</span> : null}
            <AccountControl accountSlot={accountSlot} placement="desktop" />
          </header>
        ) : null}
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
          ) : !products.length ? (
            <FirstRunWorkspace
              onOpenDemo={() => window.open("/#lead-proof", "_blank", "noopener,noreferrer")}
              onSetUp={() => setIsCreatingProduct(true)}
            />
          ) : (
            renderScreen(
              activeScreen,
              {
                listRequestId: leadListRequestId,
                view: leadWorkflowView,
                onViewChange: setLeadWorkflowView,
                onCreateAudience: startNewAudience,
                accountControl: (
                  <div className="results-account-control">
                    {accountName ? <span title={accountName}>{accountName}</span> : null}
                    <AccountControl accountSlot={accountSlot} placement="desktop" />
                  </div>
                ),
              },
              {
                defaultFolderId: newAudienceFolderId,
                onOpenAudience: (audienceId) => {
                  setLeadWorkflowView("inbox");
                  void selectProfile(audienceId)
                    .then(() => setViewMode("auto"))
                    .catch((cause) => showToast({
                      title: "Audience could not be opened",
                      message: cause instanceof Error ? cause.message : String(cause),
                      tone: "red",
                    }));
                },
              },
            )
          )}
        </main>
      </section>

      {isCreatingProduct ? (
        <AddProductDialog
          onboarding={!products.length}
          products={products}
          onClose={() => setIsCreatingProduct(false)}
          onSkip={() => {
            localStorage.setItem(onboardingStorageKey, "dismissed");
            setIsCreatingProduct(false);
          }}
          onCreate={async (input) => {
            const created = await createProductFromProfile(input);
            if (created) {
              localStorage.removeItem(onboardingStorageKey);
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
      {editFolder ? (
        <FolderEditorDialog
          folder={editFolder === "new" ? null : editFolder}
          onClose={() => setEditFolder(null)}
          onSave={async (name) => {
            if (editFolder === "new") {
              const created = await createAudienceFolder(name);
              setExpandedFolders((current) => ({ ...current, [created.id]: true }));
            } else {
              await renameAudienceFolder(editFolder.id, name);
            }
            setEditFolder(null);
          }}
        />
      ) : null}
      {deleteFolder ? (
        <DeleteFolderDialog
          folder={deleteFolder}
          onClose={() => setDeleteFolder(null)}
          onDelete={async () => {
            await deleteAudienceFolder(deleteFolder.id);
            setDeleteFolder(null);
            showToast({ title: "Folder deleted", message: "Its audiences are now unfiled.", tone: "green" });
          }}
        />
      ) : null}
      {moveAudience ? (
        <MoveAudienceDialog
          audience={moveAudience}
          folders={audienceFolders}
          onClose={() => setMoveAudience(null)}
          onMove={async (folderId) => {
            await updateProfile(moveAudience.id, { folder_id: folderId || null });
            setMoveAudience(null);
            showToast({ title: folderId ? "Audience moved" : "Audience removed from folder", tone: "green" });
          }}
        />
      ) : null}
    </div>
  );
}

function AudienceSidebarRow({
  menuOpen,
  onDelete,
  onMenuToggle,
  onMove,
  onOpen,
  onRename,
  profile,
  selected,
  switching,
}: {
  menuOpen: boolean;
  onDelete: () => void;
  onMenuToggle: () => void;
  onMove: () => void;
  onOpen: () => void;
  onRename: () => void;
  profile: Territory;
  selected: boolean;
  switching: boolean;
}) {
  return <div className="audience-list-row">
    <button className={`audience-list-main ${selected ? "active" : ""}`} aria-label={profile.label} title={profile.label} type="button" onClick={onOpen}>
      {switching ? <LoaderCircle className="lead-workspace-icon sl-spin-icon" size={15} /> : <Users className="lead-workspace-icon" size={15} />}
      <span className="audience-list-copy"><strong>{profile.label}</strong><small>{profile.place_label || profile.city} · {profile.radius_km} km</small></span>
    </button>
    <div className="audience-row-actions">
      <button aria-expanded={menuOpen} aria-label={`Actions for ${profile.label}`} type="button" onClick={onMenuToggle}><MoreVertical size={15} /></button>
      {menuOpen ? <div className="audience-sidebar-menu"><button type="button" onClick={onMove}><Folder size={13} />Move to folder</button><button type="button" onClick={onRename}><Pencil size={13} />Rename audience</button><button className="is-danger" type="button" onClick={onDelete}><Trash2 size={13} />Delete audience</button></div> : null}
    </div>
  </div>;
}

function FirstRunWorkspace({
  onOpenDemo,
  onSetUp,
}: {
  onOpenDemo: () => void;
  onSetUp: () => void;
}) {
  return (
    <section className="first-run-workspace">
      <span className="first-run-kicker">Start with your offer</span>
      <h1>Define the businesses you can help.</h1>
      <p>
        Add your business details so ScoutLead can connect your services to observable business opportunities.
      </p>
      <div className="first-run-actions">
        <button className="runbtn" type="button" onClick={onSetUp}>
          Set up ScoutLead <ArrowRight size={15} />
        </button>
        <button className="secondary" type="button" onClick={onOpenDemo}>
          <PlayCircle size={15} /> View demo workflow
        </button>
      </div>
    </section>
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
    <section className="mng" aria-label="Management">
      <p className="mng-label">Manage</p>
      <button
        className={manageItemClass(hasProduct, activeScreen === "product")}
        disabled={!hasProduct}
        aria-label="Settings"
        title="Settings"
        type="button"
        onClick={onProductSettings}
      >
        <span className="mng-icon">
          <Settings size={13} />
        </span>
        <span className="mng-label-text">Settings</span>
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
  return hasSelectedRun ? "results" : "audiences";
}

function FolderEditorDialog({
  folder,
  onClose,
  onSave,
}: {
  folder: AudienceFolder | null;
  onClose: () => void;
  onSave: (name: string) => Promise<void>;
}) {
  const [name, setName] = useState(folder?.name || "");
  const [saving, setSaving] = useState(false);
  const cleaned = name.trim();
  return <Modal title={folder ? "Rename folder" : "New folder"} onClose={onClose}>
    <form className="audience-dialog-form" onSubmit={async (event) => { event.preventDefault(); if (!cleaned || saving) return; setSaving(true); try { await onSave(cleaned); } finally { setSaving(false); } }}>
      <label><span>Folder name</span><input autoFocus maxLength={100} placeholder="For example, Roofers" value={name} onChange={(event) => setName(event.target.value)} /></label>
      <div className="modal-actions"><button className="secondary" type="button" onClick={onClose}>Cancel</button><button className="primary" disabled={!cleaned || saving} type="submit">{saving ? "Saving…" : folder ? "Save" : "Create folder"}</button></div>
    </form>
  </Modal>;
}

function DeleteFolderDialog({ folder, onClose, onDelete }: { folder: AudienceFolder; onClose: () => void; onDelete: () => Promise<void> }) {
  const [deleting, setDeleting] = useState(false);
  return <Modal title="Delete folder" onClose={onClose}>
    <div className="audience-delete-dialog"><p>Delete <strong>{folder.name}</strong>? Its audiences will remain available outside folders.</p><div className="modal-actions"><button className="secondary" type="button" onClick={onClose}>Cancel</button><button className="danger" disabled={deleting} type="button" onClick={async () => { setDeleting(true); try { await onDelete(); } finally { setDeleting(false); } }}>{deleting ? "Deleting…" : "Delete folder"}</button></div></div>
  </Modal>;
}

function MoveAudienceDialog({ audience, folders, onClose, onMove }: { audience: Territory; folders: AudienceFolder[]; onClose: () => void; onMove: (folderId: string) => Promise<void> }) {
  const [folderId, setFolderId] = useState(audience.folder_id || "");
  const [saving, setSaving] = useState(false);
  return <Modal title="Move audience" onClose={onClose}>
    <form className="audience-dialog-form" onSubmit={async (event) => { event.preventDefault(); setSaving(true); try { await onMove(folderId); } finally { setSaving(false); } }}>
      <p>Choose where <strong>{audience.label}</strong> appears in the sidebar.</p>
      <label><span>Folder</span><select value={folderId} onChange={(event) => setFolderId(event.target.value)}><option value="">No folder</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select></label>
      <div className="modal-actions"><button className="secondary" type="button" onClick={onClose}>Cancel</button><button className="primary" disabled={saving || folderId === (audience.folder_id || "")} type="submit">{saving ? "Moving…" : "Move"}</button></div>
    </form>
  </Modal>;
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
          Remove <strong>{audience.label}</strong>? Existing lead history will be retained.
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
  onboarding = false,
  products,
  onClose,
  onCreate,
  onSkip,
}: {
  onboarding?: boolean;
  products: Product[];
  onClose: () => void;
  onCreate: (input: ProductProfileInput) => Promise<Product | null>;
  onSkip?: () => void;
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
        showToast({ title: "Setup was not completed", message: "Check the business details and try again.", tone: "red" });
        return;
      }
      showToast({
        title: "Setup complete",
        message: "ScoutLead is ready for its first audience.",
        tone: "green",
      });
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setLocalError(message);
      showToast({ title: "Setup was not completed", message, tone: "red" });
    } finally {
      setCreating(false);
    }
  };

  return (
    <Modal
      className="add-product-modal"
      title="Set up your business"
      onClose={onboarding && onSkip ? onSkip : onClose}
    >
      <form
        className="add-product-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="add-product-fields">
          <label className="field add-product-name-field">
            <span>Business or offer name</span>
            <input
              autoFocus
              placeholder="Local Service Website Growth"
              value={productName}
              onChange={(event) => setProductName(event.target.value)}
            />
            {hasDuplicateProductName ? <em>This name is already in use.</em> : null}
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
          <button className="secondary" type="button" onClick={onboarding && onSkip ? onSkip : onClose}>
            {onboarding ? "Skip for now" : "Cancel"}
          </button>
          <button className="runbtn" disabled={!canCreateProduct} type="submit">
            {creating ? "Saving..." : "Complete setup"}
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

function readStoredDimension(key: string, fallback: number, min: number, max: number) {
  try {
    const stored = Number.parseInt(localStorage.getItem(key) || "", 10);
    return Number.isFinite(stored) ? Math.min(max, Math.max(min, stored)) : fallback;
  } catch {
    return fallback;
  }
}

function readStoredAppView(key: string): AppViewMode {
  try {
    const value = localStorage.getItem(key);
    return value === "auto"
      || value === "audiences"
      || value === "integrations"
      || value === "product"
      || value === "results"
      ? value
      : localStorage.getItem("selectedProfileId")
        ? "auto"
        : "audiences";
  } catch {
    return "audiences";
  }
}

function readStoredWorkflowView(key: string): LeadWorkflowView {
  try {
    const value = localStorage.getItem(key);
    return value === "inbox"
      || value === "this_week"
      || value === "shortlisted"
      || value === "contacted"
      || value === "dismissed"
      || value === "all"
      ? value
      : "inbox";
  } catch {
    return "inbox";
  }
}

function writeStoredValue(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Navigation remains usable when browser storage is disabled.
  }
}

function writeStoredDimension(key: string, value: number) {
  try {
    localStorage.setItem(key, String(Math.round(value)));
  } catch {
    // Resizing remains available when browser storage is disabled.
  }
}

function getEnabledIntegrationCount(product: Product | undefined, gmailConnected: boolean) {
  return Number(gmailConnected) + Number(Boolean(product?.webhook_enabled && product.webhook_url));
}

function isWithinLastSevenDays(value: string) {
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) && timestamp >= Date.now() - 7 * 24 * 60 * 60 * 1000;
}
