import { Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAppData } from "../state/app-data";
import { Modal, StatusPill, useToast } from "../shared-ui";
import type { ConnectionStatus } from "../types/domain";

type SavedIntegration = ConnectionStatus & {
  product_id?: string;
  product_name?: string;
};

const integrationStorageKey = "scoutlead.integrations";

export function ConnectionsScreen() {
  const { connections, products, selectedProduct } = useAppData();
  const { showToast } = useToast();
  const [showAddIntegration, setShowAddIntegration] = useState(false);
  const [savedIntegrations, setSavedIntegrations] = useState<SavedIntegration[]>([]);
  const [integrationName, setIntegrationName] = useState("Custom API");
  const [integrationCategory, setIntegrationCategory] = useState("discovery");
  const [integrationScope, setIntegrationScope] = useState<"workspace" | "product">("workspace");
  const [integrationProductId, setIntegrationProductId] = useState("");
  const [integrationDetail, setIntegrationDetail] = useState("");
  const visibleRuntimeConnections = connections.filter((connection) => connection.category !== "persistence");
  const productOptions = useMemo(() => products.map((product) => ({
    id: product.id,
    name: product.product_name,
  })), [products]);

  useEffect(() => {
    const raw = localStorage.getItem(integrationStorageKey);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) setSavedIntegrations(parsed);
    } catch {
      setSavedIntegrations([]);
    }
  }, []);

  const saveCustomIntegration = () => {
    const name = integrationName.trim();
    if (!name) {
      showToast({ title: "Integration name is required", tone: "red" });
      return;
    }
    const product = products.find((item) => item.id === integrationProductId) || selectedProduct;
    if (integrationScope === "product" && !product) {
      showToast({ title: "Select a product", message: "Create or select a product before adding a product integration.", tone: "red" });
      return;
    }
    const nextIntegration: SavedIntegration = {
      name,
      category: integrationCategory,
      status: "connected",
      detail: integrationDetail.trim() || "Configured in ScoutLead",
      product_id: integrationScope === "product" ? product?.id : undefined,
      product_name: integrationScope === "product" ? product?.product_name : undefined,
    };
    const next = [...savedIntegrations, nextIntegration];
    setSavedIntegrations(next);
    localStorage.setItem(integrationStorageKey, JSON.stringify(next));
    setShowAddIntegration(false);
    showToast({
      title: "Integration added",
      message: integrationScope === "product" && nextIntegration.product_name
        ? `${name} is attached to ${nextIntegration.product_name}.`
        : `${name} is available workspace-wide.`,
      tone: "green",
    });
  };

  return (
    <>
      <div className="integration-grid">
        <button className="integration-card integration-add-card" type="button" onClick={() => setShowAddIntegration(true)}>
          <span className="integration-logo tone-blue">
            <Plus size={18} />
          </span>
          <div>
            <strong>Add integration</strong>
            <p>Connect a discovery, reasoning, enrichment, or export provider.</p>
          </div>
        </button>

        {visibleRuntimeConnections.length === 0 && savedIntegrations.length === 0 ? (
          <article className="integration-card">
            <div>
              <strong>No connection status available</strong>
              <p>Backend `/connections/status` is not reachable yet.</p>
            </div>
          </article>
        ) : (
          [...visibleRuntimeConnections, ...savedIntegrations].map((connection, index) => (
            <ConnectionCard connection={connection} key={`${connection.category}-${connection.name}-${index}`} />
          ))
        )}
      </div>

      {showAddIntegration ? (
        <Modal title="Add integration" onClose={() => setShowAddIntegration(false)}>
          <div className="modal-form-stack">
            <label className="field">
              <span>Integration</span>
              <select value={integrationName} onChange={(event) => setIntegrationName(event.target.value)}>
                <option>Custom API</option>
                <option>Tavily</option>
                <option>Resend</option>
                <option>OpenAI</option>
                <option>Apollo</option>
              </select>
            </label>
            <label className="field">
              <span>Capability</span>
              <select value={integrationCategory} onChange={(event) => setIntegrationCategory(event.target.value)}>
                <option value="discovery">Discovery</option>
                <option value="reasoning">Reasoning</option>
                <option value="export">Export</option>
                <option value="enrichment">Enrichment</option>
              </select>
            </label>
            <label className="field">
              <span>Scope</span>
              <select value={integrationScope} onChange={(event) => setIntegrationScope(event.target.value as "workspace" | "product")}>
                <option value="workspace">Workspace</option>
                <option value="product">Selected product</option>
              </select>
            </label>
            {integrationScope === "product" ? (
              <label className="field">
                <span>Product</span>
                <select
                  value={integrationProductId || selectedProduct?.id || ""}
                  onChange={(event) => setIntegrationProductId(event.target.value)}
                >
                  {productOptions.map((product) => (
                    <option value={product.id} key={product.id}>{product.name}</option>
                  ))}
                </select>
              </label>
            ) : null}
            <label className="field">
              <span>Notes or secret reference</span>
              <input
                placeholder="Railway env var name, account note, or provider detail"
                value={integrationDetail}
                onChange={(event) => setIntegrationDetail(event.target.value)}
              />
            </label>
            <div className="form-actions">
              <button className="secondary" onClick={() => setShowAddIntegration(false)}>Cancel</button>
              <button onClick={saveCustomIntegration}>Add integration</button>
            </div>
          </div>
        </Modal>
      ) : null}
    </>
  );
}

function ConnectionCard({ connection }: { connection: SavedIntegration }) {
  const tone = connection.status === "connected" ? "green" : connection.status === "degraded" ? "amber" : "gray";
  return (
    <article className="integration-card">
      <span className={`integration-logo tone-${tone}`}>{connection.name.slice(0, 2).toUpperCase()}</span>
      <div>
        <strong>{connection.name}</strong>
        <p>{connection.product_name ? `${connection.detail} - ${connection.product_name}` : connection.detail}</p>
      </div>
      <div className="integration-side">
        <StatusPill tone={tone}>{connection.status}</StatusPill>
        <span>{connection.category}</span>
      </div>
    </article>
  );
}
