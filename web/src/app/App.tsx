import { ChevronDown, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { renderScreen } from "../routes/screen-router";
import { ToastProvider, useToast } from "../shared-ui";
import { AppDataProvider, useAppData } from "../state/app-data";
import type { Campaign, Product } from "../types/domain";
import type { Screen } from "../types/navigation";
import { navSections } from "./navigation";

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
  const [newCampaignToken, setNewCampaignToken] = useState(0);
  const [openContextMenu, setOpenContextMenu] = useState<"product" | "campaign" | null>(null);
  const contextMenuRef = useRef<HTMLDivElement | null>(null);
  const { showToast } = useToast();
  const {
    apiHealthy,
    loading,
    error,
    products,
    selectedProductId,
    setSelectedProductId,
    campaigns,
    selectedCampaign,
    selectedCampaignId,
    setSelectedCampaignId,
    connections,
    snapshot,
  } = useAppData();
  const productCampaigns = campaigns.filter((campaign) => campaign.product_id === selectedProductId);
  const visibleConnections = connections.filter((connection) => connection.category !== "persistence");
  const connectedCount = visibleConnections.filter((connection) => connection.status === "connected").length;
  const connectionTotal = visibleConnections.length || 3;
  const navCounts: Partial<Record<Screen, string>> = {
    leads: String(snapshot.metrics?.lead_count ?? snapshot.leads.length),
    trace: String(snapshot.latestAgentRun?.tool_call_count ?? 0),
    approvals: String(snapshot.metrics?.pending_approval_count ?? 0),
    conversations: String(snapshot.conversations.length),
    campaigns: String(productCampaigns.length),
  };

  const selectedProduct = products.find((product) => product.id === selectedProductId);
  const selectedProductName = selectedProduct ? displayProductName(selectedProduct) : "No product";
  const selectedCampaignName = selectedCampaign?.name || "No campaign";

  const startNewProduct = () => {
    setOpenContextMenu(null);
    setActiveScreen("product");
    setIsCreatingProduct(true);
  };

  const selectProduct = (productId: string) => {
    setOpenContextMenu(null);
    setIsCreatingProduct(false);
    setSelectedProductId(productId);
  };

  const selectCampaign = (campaignId: string) => {
    setOpenContextMenu(null);
    setSelectedCampaignId(campaignId);
  };

  const openNewCampaign = () => {
    if (!selectedProductId) return;
    setOpenContextMenu(null);
    setIsCreatingProduct(false);
    setActiveScreen("product");
    setNewCampaignToken((token) => token + 1);
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

  return (
    <div className="console">
      <aside className="rail">
        <div className="brand">
          <span className="brand-mark">S</span>
          <div>
            <strong>ScoutLead</strong>
            <span>Discovery Console</span>
          </div>
        </div>

        <nav className="nav">
          {navSections.map((section) => (
            <div className="nav-section" key={section.title}>
              <p>{section.title}</p>
              {section.items.map((screen) => {
                const Icon = screen.icon;
                const count = navCounts[screen.id] ?? screen.count;
                return (
                  <button
                    className={activeScreen === screen.id ? "nav-item active" : "nav-item"}
                    key={screen.id}
                    onClick={() => setActiveScreen(screen.id)}
                  >
                    <Icon size={15} />
                    <span>{screen.label}</span>
                    {count && <em>{count}</em>}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="rail-status">
          <span className={apiHealthy && connectedCount === connectionTotal ? "health good" : "health warn"}>
            <i />
            {apiHealthy && connectedCount === connectionTotal ? "All connected" : "Needs setup"}
          </span>
          <span>{connectedCount}/{connectionTotal}</span>
        </div>
      </aside>

      <section className="main">
        <header className="contextbar">
          <div className="context-selectors" ref={contextMenuRef}>
            <div className="context-menu-control">
              <button
                className="context-menu-trigger"
                type="button"
                onClick={() => setOpenContextMenu(openContextMenu === "product" ? null : "product")}
              >
                <span>Product</span>
                <strong>{selectedProductName}</strong>
                <ChevronDown size={14} />
              </button>
              {openContextMenu === "product" ? (
                <div className="context-menu-panel product-menu-panel">
                  {products.length ? (
                    products.map((product) => (
                      <button
                        className={product.id === selectedProductId ? "context-menu-option active" : "context-menu-option"}
                        key={product.id}
                        type="button"
                        onClick={() => selectProduct(product.id)}
                      >
                        <strong>{displayProductName(product)}</strong>
                        <span>{product.product_description || "No description saved."}</span>
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
            <span className="context-separator">/</span>
            <div className="context-menu-control campaign-context">
              <button
                className="context-menu-trigger"
                type="button"
                disabled={!selectedProductId}
                onClick={() => setOpenContextMenu(openContextMenu === "campaign" ? null : "campaign")}
              >
                <span>Campaign</span>
                <strong>{selectedCampaignName}</strong>
                {selectedCampaign ? <CampaignStatus campaign={selectedCampaign} /> : null}
                <ChevronDown size={14} />
              </button>
              {openContextMenu === "campaign" ? (
                <div className="context-menu-panel campaign-menu-panel">
                  {productCampaigns.length ? (
                    productCampaigns.map((campaign) => (
                      <button
                        className={campaign.id === selectedCampaignId ? "context-menu-option active" : "context-menu-option"}
                        key={campaign.id}
                        type="button"
                        onClick={() => selectCampaign(campaign.id)}
                      >
                        <strong>{campaign.name || "Untitled campaign"}</strong>
                        <span>{formatCampaignMeta(campaign)}</span>
                        <CampaignStatus campaign={campaign} />
                      </button>
                    ))
                  ) : (
                    <p className="context-menu-empty">No campaigns yet</p>
                  )}
                  {selectedProductId ? (
                    <button className="context-menu-create" type="button" onClick={openNewCampaign}>
                      <Plus size={14} />
                      New campaign
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
          {selectedProductId ? (
            <button className="context-primary-action" type="button" onClick={openNewCampaign}>
              <Plus size={14} />
              New campaign
            </button>
          ) : null}
        </header>
        {error && <div className="app-banner">{error}</div>}
        {loading && <div className="app-banner info">Loading campaign data...</div>}
        <main className="content">
          {renderScreen(activeScreen, setActiveScreen, {
            isCreatingProduct,
            newCampaignToken,
            onCreatingProductChange: setIsCreatingProduct,
          })}
        </main>
      </section>
    </div>
  );
}

function CampaignStatus({ campaign }: { campaign: Campaign }) {
  return (
    <span className="context-status">
      <i />
      {campaign.status.replace(/_/g, " ")}
    </span>
  );
}

function formatCampaignMeta(campaign: Campaign) {
  return `${campaign.max_leads} max leads · ${campaign.stage.replace(/_/g, " ")}`;
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
