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
    icpPresets,
  } = useAppData();
  const { showToast } = useToast();
  const [detailProductId, setDetailProductId] = useState("");
  const [productName, setProductName] = useState("");
  const [description, setDescription] = useState("");
  const [geographyDraft, setGeographyDraft] = useState("United States, Canada");
  const [creating, setCreating] = useState(false);
  const [localError, setLocalError] = useState("");
  const [showNewCampaign, setShowNewCampaign] = useState(false);
  const [campaignSource, setCampaignSource] = useState("");
  const [maxLeads, setMaxLeads] = useState("10");
  const [goalType, setGoalType] = useState<"learn" | "sell">("learn");
  const [creatingCampaign, setCreatingCampaign] = useState(false);
  const showProductCreator = isCreatingProduct;
  const canCreate = productName.trim().length > 0 && description.trim().length >= 20 && !creating;
  const detailProduct = products.find((product) => product.id === detailProductId);
  const detailCampaigns = detailProduct
    ? campaigns.filter((campaign) => campaign.product_id === detailProduct.id)
    : [];
  const campaignSetupGaps = detailProduct ? getCampaignSetupGaps(detailProduct, campaignSource) : [];
  const savedDiscoverySourceCount = detailProduct ? countDiscoverySources(detailProduct) : 0;
  const canCreateCampaign = Boolean(detailProduct) && campaignSetupGaps.length === 0 && !creatingCampaign;

  useEffect(() => {
    if (!isCreatingProduct) return;
    setProductName("");
    setDescription("");
    setGeographyDraft("United States, Canada");
    setLocalError("");
  }, [isCreatingProduct]);

  useEffect(() => {
    if (!detailProduct) return;
    setGeographyDraft(detailProduct.target_geography || "United States, Canada");
  }, [detailProduct?.id, detailProduct?.target_geography]);

  useEffect(() => {
    if (!newCampaignToken || !selectedProductId) return;
    setDetailProductId(selectedProductId);
    setCampaignSource("");
    setMaxLeads("10");
    setGoalType("learn");
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
        target_geography: "United States, Canada",
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

  const saveAdvancedSettings = async () => {
    if (!detailProduct) return;
    const targetGeography = geographyDraft.trim() || "United States, Canada";
    await updateProduct(detailProduct.id, { target_geography: targetGeography });
    showToast({ title: "Product settings saved", message: `Target geography set to ${targetGeography}.`, tone: "green" });
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
    const gaps = getCampaignSetupGaps(detailProduct, campaignSource);
    if (gaps.length) {
      showToast({
        title: "Campaign needs product setup",
        message: gaps.join(" "),
        tone: "red",
      });
      return;
    }
    setCreatingCampaign(true);
    const parsedMaxLeads = Number.parseInt(maxLeads, 10);
    const nextMaxLeads = Number.isFinite(parsedMaxLeads) ? Math.max(1, Math.min(parsedMaxLeads, 100)) : 10;
    const source = campaignSource.trim();
    try {
      const date = new Date().toISOString().slice(0, 10);
      const input: CampaignCreateInput = {
        product_id: detailProduct.id,
        name: `${displayProductName(detailProduct)} validation ${date}`,
        goal_type: goalType,
        icp_preset_id: icpPresets[0]?.id || "default-web-validation",
        source_preset_id: "google-places-local-business",
        source_input: source || null,
        max_leads: nextMaxLeads,
        channels: ["email"],
        discovery_seeds: [],
        goal_override: source ? `Discovery query override: ${source}` : null,
      };
      const created = await createCampaign(input);
      if (created) {
        setShowNewCampaign(false);
        setCampaignSource("");
        setSelectedCampaignId(created.id);
        showToast({ title: "Campaign created", message: "Run it from this product page when ready.", tone: "green" });
      } else {
        showToast({ title: "Campaign was not created", message: "Check the campaign setup and try again.", tone: "red" });
      }
    } finally {
      setCreatingCampaign(false);
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
                placeholder="Product name"
                value={productName}
                onChange={(event) => setProductName(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Product description</span>
              <textarea
                placeholder="Describe what the product does, who it is for, the problem it solves, and the outcome customers should get."
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

          <Card title="Advanced settings">
            <div className="advanced-settings-row">
              <label className="field">
                <span>Target geography</span>
                <input
                  value={geographyDraft}
                  onChange={(event) => setGeographyDraft(event.target.value)}
                  placeholder="United States, Canada"
                />
              </label>
              <button type="button" onClick={saveAdvancedSettings}>
                Save
              </button>
            </div>
          </Card>

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
            <div className="campaign-create-context">
              <span>Product</span>
              <strong>{displayProductName(detailProduct)}</strong>
              <em>{detailProduct.target_customer || "No target customer saved"}</em>
            </div>
            <div className="campaign-create-grid">
              <label className="field">
                <span>Goal</span>
                <select value={goalType} onChange={(event) => setGoalType(event.target.value as "learn" | "sell")}>
                  <option value="learn">Learn - validate ICP and book interviews</option>
                  <option value="sell">Sell - find buyers and drive product interest</option>
                </select>
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
            </div>
            <label className="field">
              <span>Discovery source</span>
              <input
                autoFocus
                placeholder="Example: residential painters in Austin, TX"
                value={campaignSource}
                onChange={(event) => setCampaignSource(event.target.value)}
              />
              <em>{formatDiscoveryHelp(campaignSource, savedDiscoverySourceCount)}</em>
            </label>
            {campaignSetupGaps.length ? (
              <div className="campaign-setup-warning" role="alert">
                <strong>Complete setup before creating this campaign</strong>
                <ul>
                  {campaignSetupGaps.map((gap) => (
                    <li key={gap}>{gap}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <div className="form-actions">
              <button className="secondary" type="button" onClick={() => setShowNewCampaign(false)}>
                Cancel
              </button>
              <button disabled={!canCreateCampaign} type="button" onClick={submitCampaign}>
                {creatingCampaign ? "Creating..." : "Create campaign"}
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

function displayProductName(product: Product) {
  const savedName = product.product_name.trim();
  if (savedName && !isGenericProductName(savedName)) return savedName;
  return inferProductName(product) || savedName || "Unnamed product";
}

function getCampaignSetupGaps(product: Product, sourceOverride: string) {
  const gaps: string[] = [];
  if (!product.target_customer.trim()) {
    gaps.push("Target customer is missing.");
  }
  if (!product.qualification_criteria.some((criterion) => criterion.label.trim())) {
    gaps.push("Qualification signals are missing.");
  }
  if (!sourceOverride.trim() && countDiscoverySources(product) === 0) {
    gaps.push("Discovery queries are missing.");
  }
  return gaps;
}

function countDiscoverySources(product: Product) {
  return product.preferred_discovery_sources.filter((source) => source.value.trim()).length;
}

function formatDiscoveryHelp(sourceOverride: string, savedSourceCount: number) {
  if (sourceOverride.trim()) {
    return "This query will be saved on the product and used for this campaign.";
  }
  if (savedSourceCount === 1) {
    return "Leave blank to use the product's generated discovery query.";
  }
  if (savedSourceCount > 1) {
    return `Leave blank to use the product's ${savedSourceCount} generated discovery queries.`;
  }
  return "Add a query here, or update the product profile with discovery queries before creating a campaign.";
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
