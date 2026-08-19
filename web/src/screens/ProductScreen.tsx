import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, Modal, StatusPill, useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { Campaign, CampaignCreateInput, Product } from "../types/domain";
import type { Screen } from "../types/navigation";
import { statusTone } from "../utils/status";

type ProductScreenProps = {
  isCreatingProduct: boolean;
  newCampaignToken: number;
  onCreatingProductChange: (isCreating: boolean) => void;
  onNavigate: (screen: Screen) => void;
};

export function ProductScreen({
  isCreatingProduct,
  newCampaignToken,
  onCreatingProductChange,
  onNavigate,
}: ProductScreenProps) {
  const {
    products,
    selectedProductId,
    setSelectedProductId,
    setSelectedCampaignId,
    campaigns,
    createProductFromDescription,
    createCampaign,
    deleteProduct,
    updateProduct,
    runCampaign,
    pauseCampaign,
    resumeCampaign,
  } = useAppData();
  const { showToast } = useToast();
  const [detailProductId, setDetailProductId] = useState("");
  const [productName, setProductName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [localError, setLocalError] = useState("");
  const [showNewCampaign, setShowNewCampaign] = useState(false);
  const [campaignSource, setCampaignSource] = useState("");
  const [maxLeads, setMaxLeads] = useState("10");
  const [toolPlan, setToolPlan] = useState({
    search: true,
    websiteResearch: true,
    reasoning: true,
    outreachDrafts: true,
  });
  const showProductCreator = isCreatingProduct;
  const canCreate = productName.trim().length > 0 && description.trim().length >= 20 && !creating;
  const detailProduct = products.find((product) => product.id === detailProductId);
  const detailCampaigns = detailProduct
    ? campaigns.filter((campaign) => campaign.product_id === detailProduct.id)
    : [];

  useEffect(() => {
    if (!isCreatingProduct) return;
    setProductName("");
    setDescription("");
    setLocalError("");
  }, [isCreatingProduct]);

  useEffect(() => {
    if (!newCampaignToken || !selectedProductId) return;
    setDetailProductId(selectedProductId);
    setCampaignSource("");
    setMaxLeads("10");
    setToolPlan({
      search: true,
      websiteResearch: true,
      reasoning: true,
      outreachDrafts: true,
    });
    setShowNewCampaign(true);
  }, [newCampaignToken, selectedProductId]);

  useEffect(() => {
    if (isCreatingProduct || !selectedProductId) return;
    setDetailProductId((current) => current || selectedProductId);
  }, [isCreatingProduct, selectedProductId]);

  const startCreatingProduct = () => {
    setProductName("");
    setDescription("");
    setLocalError("");
    onCreatingProductChange(true);
    setDetailProductId("");
  };

  const selectProduct = (productId: string) => {
    setSelectedProductId(productId);
    onCreatingProductChange(false);
    setLocalError("");
    setDetailProductId(productId);
  };

  const createFromDescription = async () => {
    if (!canCreate) return;
    setCreating(true);
    setLocalError("");
    try {
      const created = await createProductFromDescription({
        product_name: productName.trim(),
        description: description.trim(),
        target_geography: "United States",
      });
      if (created) {
        setProductName("");
        setDescription("");
        onCreatingProductChange(false);
        setSelectedProductId(created.id);
        setDetailProductId(created.id);
        showToast({ title: "Product created", message: `${productName.trim()} is ready for campaigns.`, tone: "green" });
      } else {
        showToast({ title: "Product was not created", message: "Check the product details and try again.", tone: "red" });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setLocalError(message);
      showToast({ title: "Product was not created", message, tone: "red" });
    } finally {
      setCreating(false);
    }
  };

  const deleteSelectedProduct = async () => {
    if (!detailProduct) return;
    const campaignCount = detailCampaigns.length;
    const confirmed = window.confirm(
      `Delete ${displayProductName(detailProduct)}? This also deletes ${campaignCount} related campaign${campaignCount === 1 ? "" : "s"} and all leads, messages, conversations, and agent records for this product.`,
    );
    if (!confirmed) return;
    await deleteProduct(detailProduct.id);
    setDetailProductId("");
    showToast({ title: "Product deleted", message: `${displayProductName(detailProduct)} was removed.`, tone: "green" });
  };

  const submitCampaign = async () => {
    if (!detailProduct) return;
    const parsedMaxLeads = Number.parseInt(maxLeads, 10);
    const nextMaxLeads = Number.isFinite(parsedMaxLeads) ? Math.max(1, Math.min(parsedMaxLeads, 100)) : 10;
    const source = campaignSource.trim();
    if (source) {
      await updateProduct(detailProduct.id, {
        preferred_discovery_sources: [{ type: "web_search", value: source, limit: nextMaxLeads }],
      });
    }
    const enabledTools = Object.entries(toolPlan)
      .filter(([, enabled]) => enabled)
      .map(([tool]) => tool.replace(/([A-Z])/g, " $1").toLowerCase());
    const date = new Date().toISOString().slice(0, 10);
    const input: CampaignCreateInput = {
      product_id: detailProduct.id,
      name: `${displayProductName(detailProduct)} validation ${date}`,
      max_leads: nextMaxLeads,
      channels: ["email"],
      discovery_seeds: [],
      goal_override: `Tool plan: ${enabledTools.join(", ")}${source ? `. Discovery source: ${source}` : ""}`,
    };
    const created = await createCampaign(input);
    if (created) {
      setShowNewCampaign(false);
      setSelectedCampaignId(created.id);
      showToast({ title: "Campaign created", message: "Run it from this product page when ready.", tone: "green" });
    } else {
      showToast({ title: "Campaign was not created", message: "Check the campaign setup and try again.", tone: "red" });
    }
  };

  return (
    <div className="product-page">
      {showProductCreator ? (
        <Modal title="Add product" onClose={() => onCreatingProductChange(false)}>
          <form
            className="product-description-create"
            onSubmit={(event) => {
              event.preventDefault();
              void createFromDescription();
            }}
          >
            <label className="field">
              <span>Product name</span>
              <input
                autoFocus
                placeholder="QuoteVan"
                value={productName}
                onChange={(event) => setProductName(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Product description</span>
              <textarea
                placeholder="Example: QuoteVan helps home-service painters capture job scope during a walkthrough, send a professional quote before leaving the job, and keep customer history in one place."
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            <div className="form-actions">
              {products.length > 0 ? (
                <button className="secondary" type="button" onClick={() => onCreatingProductChange(false)}>
                  Cancel
                </button>
              ) : null}
              <button disabled={!canCreate} type="submit">
                {creating ? "Creating..." : "Create product"}
              </button>
            </div>
          </form>

          {localError ? <p className="form-error">{localError}</p> : null}
        </Modal>
      ) : null}

      {!showProductCreator && !detailProduct ? (
        <Card
          title="Product list"
          meta={
            <div className="card-actions">
              <span className="muted-count">{products.length} total</span>
              <button className="icon-action" type="button" aria-label="Add product" onClick={startCreatingProduct}>
                <Plus size={18} />
              </button>
            </div>
          }
        >
          <div className="product-table">
            <div className="product-table-head">
              <span>Product</span>
              <span>Description</span>
            </div>
            {products.map((product) => (
              <button
                className={product.id === selectedProductId ? "product-table-row active" : "product-table-row"}
                key={product.id}
                type="button"
                onClick={() => selectProduct(product.id)}
              >
                <strong>{displayProductName(product)}</strong>
                <span>{product.product_description || "No description saved."}</span>
              </button>
            ))}
          </div>
        </Card>
      ) : null}

      {!showProductCreator && detailProduct ? (
        <div className="product-detail-stack">
          <Card
            title="Profile"
            meta={
              <div className="card-actions">
                <button className="secondary" type="button" onClick={() => setDetailProductId("")}>
                  Back
                </button>
                <StatusPill tone="green">Active</StatusPill>
                <button className="danger" onClick={deleteSelectedProduct}>
                  <Trash2 size={14} />
                  Delete
                </button>
              </div>
            }
          >
            <p className="product-brief">{detailProduct.product_description}</p>
            <div className="product-facts">
              <ProductFact label="ICP" value={detailProduct.target_customer} />
              <ProductFact label="Goal" value={detailProduct.validation_goal} />
              <ProductFact label="Region" value={detailProduct.target_geography} />
            </div>
          </Card>

          <div className="product-profile-grid">
            <Card title="Qualification signals">
              <div className="signal-list">
                {detailProduct.qualification_criteria.map((criterion, index) => (
                  <div className="signal-row" key={criterion.id || criterion.label}>
                    <span>{index + 1}</span>
                    <div>
                      <strong>{cleanCriterionLabel(criterion.label)}</strong>
                      {criterion.description ? <em>{criterion.description}</em> : null}
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            <Card title="Discovery queries">
              <div className="query-list">
                {detailProduct.preferred_discovery_sources.map((discoverySource) => (
                  <div className="query-row" key={`${discoverySource.type}:${discoverySource.value}`}>
                    <span>{formatDiscoveryType(discoverySource.type)}</span>
                    <strong>{discoverySource.value}</strong>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <Card
            title="Campaigns"
            meta={
              <div className="card-actions">
                <span className="muted-count">{detailCampaigns.length} campaigns</span>
              </div>
            }
          >
            <div className="history-list">
              <HistoryRow label="Created" value={formatDate(detailProduct.created_at)} />
              <HistoryRow label="Updated" value={formatDate(detailProduct.updated_at)} />
              {detailCampaigns.map((campaign) => (
                <ProductCampaignRow
                  campaign={campaign}
                  key={campaign.id}
                  onOpen={() => setSelectedCampaignId(campaign.id)}
                  onRun={() => runCampaign(campaign.id)}
                  onPause={() => pauseCampaign(campaign.id)}
                  onResume={() => resumeCampaign(campaign.id)}
                  onReview={() => {
                    setSelectedCampaignId(campaign.id);
                    onNavigate("approvals");
                  }}
                />
              ))}
              {!detailCampaigns.length ? <p className="empty-copy">No campaigns have been run for this product.</p> : null}
            </div>
          </Card>
        </div>
      ) : null}

      {showNewCampaign && detailProduct ? (
        <Modal title="New campaign" onClose={() => setShowNewCampaign(false)}>
          <div className="campaign-create-modal">
            <label className="field">
              <span>Discovery source</span>
              <input
                autoFocus
                placeholder="residential painters Austin Texas"
                value={campaignSource}
                onChange={(event) => setCampaignSource(event.target.value)}
              />
              <em>Blank uses this product's saved discovery queries.</em>
            </label>
            <label className="field">
              <span>Max leads</span>
              <input
                min={1}
                max={100}
                type="number"
                value={maxLeads}
                onChange={(event) => setMaxLeads(event.target.value)}
              />
            </label>
            <div className="tool-toggle-list">
              <strong>Tools for this campaign</strong>
              {Object.entries(toolPlan).map(([key, enabled]) => (
                <label key={key}>
                  <input
                    checked={enabled}
                    type="checkbox"
                    onChange={(event) =>
                      setToolPlan((current) => ({ ...current, [key]: event.target.checked }))
                    }
                  />
                  <span>{formatToolName(key)}</span>
                </label>
              ))}
            </div>
            <div className="form-actions">
              <button className="secondary" type="button" onClick={() => setShowNewCampaign(false)}>
                Cancel
              </button>
              <button type="button" onClick={submitCampaign}>
                Create campaign
              </button>
            </div>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

function ProductFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="product-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ProductCampaignRow({
  campaign,
  onOpen,
  onRun,
  onPause,
  onResume,
  onReview,
}: {
  campaign: Campaign;
  onOpen: () => void;
  onRun: () => void;
  onPause: () => void;
  onResume: () => void;
  onReview: () => void;
}) {
  return (
    <div className="campaign-history-row">
      <button className="link-button" type="button" onClick={onOpen}>
        <strong>{campaign.name || "Untitled campaign"}</strong>
        <span>{campaign.id}</span>
      </button>
      <StatusPill tone={statusTone(campaign.status)}>{campaign.status.replace(/_/g, " ")}</StatusPill>
      <time>{formatDate(campaign.created_at)}</time>
      <CampaignAction
        status={campaign.status}
        onRun={onRun}
        onPause={onPause}
        onResume={onResume}
        onReview={onReview}
      />
    </div>
  );
}

function CampaignAction({
  status,
  onRun,
  onPause,
  onResume,
  onReview,
}: {
  status: string;
  onRun: () => void;
  onPause: () => void;
  onResume: () => void;
  onReview: () => void;
}) {
  if (status === "draft" || status === "failed") {
    return <button type="button" onClick={onRun}>Run</button>;
  }
  if (status === "paused") {
    return <button type="button" onClick={onResume}>Resume</button>;
  }
  if (status === "awaiting_approval") {
    return <button type="button" onClick={onReview}>Review</button>;
  }
  if (["discovering", "researching", "qualifying", "drafting_outreach", "sending"].includes(status)) {
    return <button className="secondary" type="button" onClick={onPause}>Pause</button>;
  }
  return <button className="secondary" type="button" onClick={onReview}>Open</button>;
}

function cleanCriterionLabel(label: string) {
  return label.replace(/^Matches target customer:\s*/i, "");
}

function formatDiscoveryType(type: string) {
  return type.replace("_", " ");
}

function formatToolName(value: string) {
  return value.replace(/([A-Z])/g, " $1").replace(/^./, (letter) => letter.toUpperCase());
}

function displayProductName(product: Product) {
  const savedName = product.product_name.trim();
  if (savedName && !isGenericProductName(savedName)) return savedName;
  return inferProductName(product) || savedName || "Unnamed product";
}

function isGenericProductName(name: string) {
  return /^(new product|untitled product|product)$/i.test(name.trim());
}

function inferProductName(product: Product) {
  const evidence = product.source_evidence;
  const candidates = Array.isArray(evidence?.product_name_candidates)
    ? evidence.product_name_candidates
    : [];
  const evidenceName = candidates.find(
    (candidate): candidate is string =>
      typeof candidate === "string" && candidate.trim().length > 0 && !isGenericProductName(candidate),
  );
  if (evidenceName) return evidenceName.trim();

  const text = product.product_description.trim();
  const labeledName = text.match(
    /(?:one-liner|short(?:\s*\([^)]*\))?|headline)\s*:\s*([A-Z][A-Za-z0-9._-]{1,60})\b/i,
  );
  if (labeledName?.[1] && !isGenericProductName(labeledName[1])) return labeledName[1];

  const sentenceStartName = text.match(
    /^([A-Z][A-Za-z0-9._-]{1,60})\s+(?:is|helps|turns|lets|allows|enables|gives|provides)\b/,
  );
  if (sentenceStartName?.[1] && !isGenericProductName(sentenceStartName[1])) return sentenceStartName[1];

  return "";
}

function HistoryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="history-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}
