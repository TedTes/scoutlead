import { Plus } from "lucide-react";
import { useState } from "react";
import { renderScreen } from "../routes/screen-router";
import { AppDataProvider, useAppData } from "../state/app-data";
import type { Product } from "../types/domain";
import type { Screen } from "../types/navigation";
import { screens } from "./navigation";

export function App() {
  return (
    <AppDataProvider>
      <AppShell />
    </AppDataProvider>
  );
}

function AppShell() {
  const [activeScreen, setActiveScreen] = useState<Screen>("overview");
  const [isCreatingProduct, setIsCreatingProduct] = useState(false);
  const [newProductToken, setNewProductToken] = useState(0);
  const {
    apiHealthy,
    loading,
    error,
    products,
    selectedProductId,
    setSelectedProductId,
    campaigns,
    snapshot,
  } = useAppData();
  const navCounts: Partial<Record<Screen, string>> = {
    campaigns: String(campaigns.length),
    leads: String(snapshot.metrics?.lead_count ?? snapshot.leads.length),
    approvals: String(snapshot.metrics?.pending_approval_count ?? 0),
    conversations: String(snapshot.conversations.length),
  };
  const selectProduct = (productId: string) => {
    setIsCreatingProduct(false);
    setSelectedProductId(productId);
  };
  const startNewProduct = () => {
    setActiveScreen("product");
    setIsCreatingProduct(true);
    setNewProductToken((token) => token + 1);
  };

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
          <p>Workflow</p>
          {screens.map((screen) => {
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
        </nav>

        <div className="rail-status">
          <span className={apiHealthy ? "health good" : "health warn"}>
            <i />
            {apiHealthy ? "API healthy" : "API offline"}
          </span>
          <span>4/5 live</span>
        </div>
      </aside>

      <section className="main">
        <header className="commandbar">
          <div className="crumb">
            <ProductBreadcrumbSelect
              isCreatingProduct={isCreatingProduct && activeScreen === "product"}
              products={products}
              selectedProductId={selectedProductId}
              onSelectProduct={selectProduct}
            />
            <button className="crumb-add-product" type="button" aria-label="Add product" onClick={startNewProduct}>
              <Plus size={16} />
            </button>
          </div>
        </header>

        {error && <div className="app-banner">{error}</div>}
        {loading && <div className="app-banner info">Loading campaign data...</div>}
        <main className="content">
          {renderScreen(activeScreen, setActiveScreen, {
            isCreatingProduct,
            newProductToken,
            onCreatingProductChange: setIsCreatingProduct,
          })}
        </main>
      </section>
    </div>
  );
}

function ProductBreadcrumbSelect({
  isCreatingProduct,
  products,
  selectedProductId,
  onSelectProduct,
}: {
  isCreatingProduct: boolean;
  products: Product[];
  selectedProductId: string;
  onSelectProduct: (productId: string) => void;
}) {
  const value = isCreatingProduct ? "__new_product__" : selectedProductId;

  return (
    <select
      className="crumb-product-select"
      value={value}
      onChange={(event) => onSelectProduct(event.target.value)}
    >
      {isCreatingProduct ? <option value="__new_product__">New product</option> : null}
      <option value="">No product</option>
      {products.map((product) => (
        <option value={product.id} key={product.id}>
          {product.product_name}
        </option>
      ))}
    </select>
  );
}
