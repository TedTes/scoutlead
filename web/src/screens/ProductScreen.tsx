import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, Modal, StatusPill, useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { Campaign, CampaignCreateInput, Product, ProductIcpSuggestion } from "../types/domain";
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
    suggestProductIcps,
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
  const [setupGeography, setSetupGeography] = useState("United States, Canada");
  const [icpSuggestions, setIcpSuggestions] = useState<ProductIcpSuggestion[]>([]);
  const [selectedSuggestionIndex, setSelectedSuggestionIndex] = useState<number | null>(null);
  const [targetCustomerDraft, setTargetCustomerDraft] = useState("");
  const [problemDraft, setProblemDraft] = useState("");
  const [valueDraft, setValueDraft] = useState("");
  const [discoveryQueryDraft, setDiscoveryQueryDraft] = useState("");
  const [qualificationSignalsDraft, setQualificationSignalsDraft] = useState("");
  const [geographyDraft, setGeographyDraft] = useState("United States, Canada");
  const [creating, setCreating] = useState(false);
  const [generatingSegments, setGeneratingSegments] = useState(false);
  const [localError, setLocalError] = useState("");
  const [showNewCampaign, setShowNewCampaign] = useState(false);
  const [campaignLocation, setCampaignLocation] = useState("");
  const [maxLeads, setMaxLeads] = useState("10");
  const [goalType, setGoalType] = useState<"learn" | "sell">("learn");
  const [creatingCampaign, setCreatingCampaign] = useState(false);
  const showProductCreator = isCreatingProduct;
  const canCreateProduct = productName.trim().length > 0 && description.trim().length >= 20 && !creating;
  const canApplyIcp =
    Boolean(detailProductId) &&
    selectedSuggestionIndex !== null &&
    targetCustomerDraft.trim().length > 0 &&
    problemDraft.trim().length > 0 &&
    valueDraft.trim().length > 0 &&
    discoveryQueryDraft.trim().length > 0 &&
    qualificationSignalsDraft.split("\n").some((signal) => signal.trim()) &&
    !creating;
  const detailProduct = products.find((product) => product.id === detailProductId);
  const detailCampaigns = detailProduct
    ? campaigns.filter((campaign) => campaign.product_id === detailProduct.id)
    : [];
  const campaignSetupGaps = detailProduct ? getCampaignSetupGaps(detailProduct, campaignLocation) : [];
  const savedDiscoverySourceCount = detailProduct ? countDiscoverySources(detailProduct) : 0;
  const suggestedCampaignLocations = detailProduct ? getSuggestedCampaignLocations(detailProduct) : [];
  const canCreateCampaign = Boolean(detailProduct) && campaignSetupGaps.length === 0 && !creatingCampaign;
  const canGenerateSegments = Boolean(detailProduct) && !generatingSegments;

  useEffect(() => {
    if (!isCreatingProduct) return;
    setProductName("");
    setDescription("");
    setSetupGeography("United States, Canada");
    setGeographyDraft("United States, Canada");
    setLocalError("");
  }, [isCreatingProduct]);

  useEffect(() => {
    if (!detailProduct) return;
    setGeographyDraft(detailProduct.target_geography || "United States, Canada");
    setIcpSuggestions(getProductIcpSuggestions(detailProduct));
    clearIcpDraft();
  }, [detailProduct?.id, detailProduct?.target_geography, detailProduct?.updated_at]);

  useEffect(() => {
    if (!newCampaignToken || !selectedProductId) return;
    const product = products.find((item) => item.id === selectedProductId);
    setDetailProductId(selectedProductId);
    setCampaignLocation(product ? getDefaultCampaignLocation(product) : "");
    setMaxLeads("10");
    setGoalType("learn");
    setShowNewCampaign(true);
  }, [newCampaignToken, selectedProductId, products]);

  useEffect(() => {
    if (isCreatingProduct || !selectedProductId) return;
    setDetailProductId((current) => current || selectedProductId);
  }, [isCreatingProduct, selectedProductId]);

  const startCreatingProduct = () => {
    setProductName("");
    setDescription("");
    setSetupGeography("United States, Canada");
    clearIcpDraft();
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
    if (!canCreateProduct) return;
    setCreating(true);
    setLocalError("");
    try {
      const created = await createProductFromDescription({
        product_name: productName.trim(),
        description: description.trim(),
        target_geography: setupGeography.trim() || "United States, Canada",
      });
      if (created) {
        setProductName("");
        setDescription("");
        setSetupGeography("United States, Canada");
        onCreatingProductChange(false);
        setSelectedProductId(created.id);
        setDetailProductId(created.id);
        showToast({
          title: "Product created",
          message: "Generate customer segments from the product profile when ready.",
          tone: "green",
        });
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

  const generateIcpSuggestions = async () => {
    if (!detailProduct) return;
    if (!canGenerateSegments) return;
    setGeneratingSegments(true);
    setLocalError("");
    try {
      const result = await suggestProductIcps({
        product_name: displayProductName(detailProduct),
        description: detailProduct.product_description,
        target_geography: detailProduct.target_geography || "United States, Canada",
      });
      if (result?.suggestions.length) {
        setIcpSuggestions(result.suggestions);
        clearIcpDraft();
        await updateProduct(detailProduct.id, {
          source_evidence: {
            ...getProductEvidence(detailProduct),
            icp_suggestions: result.suggestions,
            icp_suggestions_generated_at: new Date().toISOString(),
          },
        });
        showToast({ title: "Segments generated", message: "Pick one customer segment to test.", tone: "green" });
      } else {
        showToast({ title: "No segments generated", message: "Add more product context and try again.", tone: "red" });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setLocalError(message);
      showToast({ title: "Could not generate segments", message, tone: "red" });
    } finally {
      setGeneratingSegments(false);
    }
  };

  const selectSuggestion = (suggestion: ProductIcpSuggestion, index: number) => {
    setSelectedSuggestionIndex(index);
    setTargetCustomerDraft(suggestion.target_customer);
    setProblemDraft(suggestion.likely_pain);
    setValueDraft(suggestion.value_hypothesis);
    setDiscoveryQueryDraft(suggestion.discovery_query);
    setQualificationSignalsDraft(suggestion.qualification_signals.join("\n"));
  };

  const applySelectedIcp = async () => {
    if (!detailProduct || !canApplyIcp) return;
    const selectedSuggestion =
      selectedSuggestionIndex === null ? null : icpSuggestions[selectedSuggestionIndex] || null;
    setCreating(true);
    setLocalError("");
    try {
      const signals = qualificationSignalsDraft
        .split("\n")
        .map((signal) => signal.trim())
        .filter(Boolean);
      await updateProduct(detailProduct.id, {
        target_customer: targetCustomerDraft.trim(),
        problem_being_solved: problemDraft.trim(),
        value_proposition: valueDraft.trim(),
        validation_goal: `Book customer discovery interviews with ${targetCustomerDraft.trim()}.`,
        qualification_criteria: signals.map((signal, index) => ({
          label: signal,
          description: null,
          weight: index === 0 ? 3 : 2,
          required: index === 0,
          evidence_required: true,
        })),
        preferred_discovery_sources: [
          {
            type: "web_search",
            value: discoveryQueryDraft.trim(),
            limit: null,
            notes: "Generated from selected customer segment.",
          },
        ],
        outreach_objective: "Ask for a short customer discovery conversation.",
        constraints: ensureHumanApprovalConstraint(detailProduct.constraints),
        source_evidence: {
          ...getProductEvidence(detailProduct),
          selected_icp: selectedSuggestion,
          config_generated_by: "llm_icp_suggestion",
          profile_status: "confirmed",
        },
      });
      clearIcpDraft();
      showToast({ title: "ICP applied", message: "The product is ready for a campaign.", tone: "green" });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setLocalError(message);
      showToast({ title: "ICP was not applied", message, tone: "red" });
    } finally {
      setCreating(false);
    }
  };

  const clearIcpDraft = () => {
    setSelectedSuggestionIndex(null);
    setTargetCustomerDraft("");
    setProblemDraft("");
    setValueDraft("");
    setDiscoveryQueryDraft("");
    setQualificationSignalsDraft("");
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
    const gaps = getCampaignSetupGaps(detailProduct, campaignLocation);
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
    const location = campaignLocation.trim();
    const source = buildCampaignDiscoveryQuery(detailProduct, location);
    try {
      const date = new Date().toISOString().slice(0, 10);
      const input: CampaignCreateInput = {
        product_id: detailProduct.id,
        name: `${displayProductName(detailProduct)} validation ${date}`,
        goal_type: goalType,
        icp_preset_id: icpPresets[0]?.id || "default-web-validation",
        source_preset_id: "google-places-local-business",
        source_input: source,
        max_leads: nextMaxLeads,
        channels: ["email"],
        discovery_seeds: [],
        goal_override: `Campaign location: ${location}`,
      };
      const created = await createCampaign(input);
      if (created) {
        setShowNewCampaign(false);
        setCampaignLocation("");
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
            <label className="field">
              <span>Starting geography</span>
              <input
                placeholder="Example: Austin TX"
                value={setupGeography}
                onChange={(event) => setSetupGeography(event.target.value)}
              />
            </label>
            <div className="form-actions">
              {products.length > 0 ? (
                <button className="secondary" type="button" onClick={() => onCreatingProductChange(false)}>
                  Cancel
                </button>
              ) : null}
              <button disabled={!canCreateProduct} type="submit">
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
            {!isProductIcpConfigured(detailProduct) ? (
              <p className="product-setup-note">Choose a customer segment before creating a campaign.</p>
            ) : null}
            <div className="product-facts">
              <ProductFact
                label="ICP"
                value={isProductIcpConfigured(detailProduct) ? detailProduct.target_customer : "Not selected"}
              />
              <ProductFact
                label="Goal"
                value={isProductIcpConfigured(detailProduct) ? detailProduct.validation_goal : "Not configured"}
              />
              <ProductFact label="Region" value={detailProduct.target_geography} />
            </div>
          </Card>

          <Card
            title="Customer segments"
            meta={
              <button disabled={!canGenerateSegments} type="button" onClick={generateIcpSuggestions}>
                {generatingSegments ? "Generating..." : icpSuggestions.length ? "Regenerate" : "Generate ICP suggestions"}
              </button>
            }
          >
            {icpSuggestions.length ? (
              <div className="icp-suggestion-flow no-divider">
                <div className="icp-suggestion-list">
                  {icpSuggestions.map((suggestion, index) => (
                    <button
                      className={selectedSuggestionIndex === index ? "icp-suggestion-card active" : "icp-suggestion-card"}
                      key={`${suggestion.segment_name}:${index}`}
                      type="button"
                      onClick={() => selectSuggestion(suggestion, index)}
                    >
                      <strong>{suggestion.segment_name}</strong>
                      <span>{suggestion.why_this_segment}</span>
                      <em>{suggestion.discovery_query}</em>
                      {suggestion.suggested_locations?.length ? (
                        <small>{suggestion.suggested_locations.slice(0, 3).join(" / ")}</small>
                      ) : null}
                    </button>
                  ))}
                </div>

                {selectedSuggestionIndex !== null ? (
                  <div className="icp-selected-editor">
                    <div className="icp-edit-grid">
                      <label className="field">
                        <span>Target customer</span>
                        <input
                          value={targetCustomerDraft}
                          onChange={(event) => setTargetCustomerDraft(event.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>Discovery query</span>
                        <input
                          value={discoveryQueryDraft}
                          onChange={(event) => setDiscoveryQueryDraft(event.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>Problem to validate</span>
                        <textarea
                          value={problemDraft}
                          onChange={(event) => setProblemDraft(event.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>Value hypothesis</span>
                        <textarea
                          value={valueDraft}
                          onChange={(event) => setValueDraft(event.target.value)}
                        />
                      </label>
                      <label className="field icp-signals-field">
                        <span>Qualification signals</span>
                        <textarea
                          value={qualificationSignalsDraft}
                          onChange={(event) => setQualificationSignalsDraft(event.target.value)}
                        />
                      </label>
                    </div>
                    <div className="form-actions">
                      <button className="secondary" type="button" onClick={clearIcpDraft}>
                        Cancel
                      </button>
                      <button disabled={!canApplyIcp} type="button" onClick={applySelectedIcp}>
                        {creating ? "Applying..." : "Apply segment"}
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="empty-copy">No customer segment hypotheses have been generated for this product.</p>
            )}
          </Card>

          <div className="product-profile-grid">
            <Card title="Qualification signals">
              {isProductIcpConfigured(detailProduct) ? (
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
              ) : (
                <p className="empty-copy">Apply a customer segment to define qualification signals.</p>
              )}
            </Card>

            <Card title="Discovery queries">
              {detailProduct.preferred_discovery_sources.length ? (
                <div className="query-list">
                  {detailProduct.preferred_discovery_sources.map((discoverySource) => (
                  <div className="query-row" key={`${discoverySource.type}:${discoverySource.value}`}>
                    <span>{formatDiscoveryType(discoverySource.type)}</span>
                    <strong>{discoverySource.value}</strong>
                  </div>
                  ))}
                </div>
              ) : (
                <p className="empty-copy">Apply a customer segment to define a discovery query.</p>
              )}
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
              <span>Campaign location</span>
              <input
                autoFocus
                placeholder="Example: Toronto, ON, Canada"
                value={campaignLocation}
                onChange={(event) => setCampaignLocation(event.target.value)}
              />
              <em>{formatDiscoveryHelp(detailProduct, campaignLocation, savedDiscoverySourceCount)}</em>
            </label>
            {suggestedCampaignLocations.length ? (
              <div className="location-suggestion-row" aria-label="Suggested campaign locations">
                {suggestedCampaignLocations.map((location) => (
                  <button
                    className={campaignLocation === location ? "chip-button active" : "chip-button"}
                    key={location}
                    type="button"
                    onClick={() => setCampaignLocation(location)}
                  >
                    {location}
                  </button>
                ))}
              </div>
            ) : null}
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

function getCampaignSetupGaps(product: Product, location: string) {
  const gaps: string[] = [];
  if (!isProductIcpConfigured(product)) {
    gaps.push("Choose and apply a customer segment.");
  }
  if (!product.qualification_criteria.some((criterion) => criterion.label.trim())) {
    gaps.push("Qualification signals are missing.");
  }
  if (!getPrimaryDiscoveryQuery(product)) {
    gaps.push("Discovery queries are missing.");
  }
  if (!location.trim()) {
    gaps.push("Campaign location is missing.");
  }
  return gaps;
}

function isProductIcpConfigured(product: Product) {
  const targetCustomer = product.target_customer.trim();
  const profileStatus = getProductEvidence(product).profile_status;
  const hasDraftPlaceholder =
    /^define target customer before running discovery\.$/i.test(targetCustomer) ||
    product.qualification_criteria.some((criterion) =>
      /^target customer fit needs setup$/i.test(criterion.label.trim()),
    );
  if (profileStatus === "draft") return false;
  if (profileStatus === "confirmed") return !hasDraftPlaceholder;
  return Boolean(targetCustomer) && !hasDraftPlaceholder;
}

function countDiscoverySources(product: Product) {
  return product.preferred_discovery_sources.filter((source) => source.value.trim()).length;
}

function formatDiscoveryHelp(product: Product, location: string, savedSourceCount: number) {
  const query = getPrimaryDiscoveryQuery(product);
  if (!query) {
    return "Apply a customer segment first so ScoutLead knows which business category to search.";
  }
  if (!location.trim()) {
    return `ScoutLead will combine this location with "${query}".`;
  }
  const sourceCountCopy =
    savedSourceCount > 1 ? `${savedSourceCount} saved discovery queries` : "the saved discovery query";
  return `Search: "${buildCampaignDiscoveryQuery(product, location)}" using ${sourceCountCopy}.`;
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

function getProductEvidence(product: Product): Record<string, unknown> {
  const evidence = product.source_evidence;
  if (!evidence || typeof evidence !== "object" || Array.isArray(evidence)) return {};
  return evidence;
}

function getProductIcpSuggestions(product: Product): ProductIcpSuggestion[] {
  const value = getProductEvidence(product).icp_suggestions;
  if (!Array.isArray(value)) return [];
  return value.filter(isProductIcpSuggestion);
}

function getSuggestedCampaignLocations(product: Product) {
  const selectedIcp = getProductEvidence(product).selected_icp;
  if (isProductIcpSuggestion(selectedIcp)) return selectedIcp.suggested_locations || [];
  return getProductIcpSuggestions(product).flatMap((suggestion) => suggestion.suggested_locations || []);
}

function getDefaultCampaignLocation(product: Product) {
  return getSuggestedCampaignLocations(product)[0] || (isBroadGeography(product.target_geography) ? "" : product.target_geography);
}

function getPrimaryDiscoveryQuery(product: Product) {
  return product.preferred_discovery_sources.find((source) => source.value.trim())?.value.trim() || "";
}

function buildCampaignDiscoveryQuery(product: Product, location: string) {
  const query = stripBroadGeographyTerms(getPrimaryDiscoveryQuery(product));
  const normalizedLocation = location.trim();
  if (!query) return normalizedLocation;
  if (!normalizedLocation) return query;
  if (query.toLowerCase().includes(normalizedLocation.toLowerCase())) return query;
  return `${query} ${normalizedLocation}`.replace(/\s+/g, " ").trim();
}

function stripBroadGeographyTerms(query: string) {
  return query
    .replace(/\b(united states,\s*canada|united states and canada|north america|united states|usa|canada|us)\b/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}

function isBroadGeography(value: string) {
  const normalized = value.trim().toLowerCase().replace("&", "and");
  return [
    "united states",
    "usa",
    "us",
    "canada",
    "north america",
    "united states, canada",
    "united states and canada",
  ].includes(normalized);
}

function isProductIcpSuggestion(value: unknown): value is ProductIcpSuggestion {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const candidate = value as Partial<ProductIcpSuggestion>;
  return (
    typeof candidate.segment_name === "string" &&
    typeof candidate.target_customer === "string" &&
    typeof candidate.why_this_segment === "string" &&
    typeof candidate.likely_pain === "string" &&
    typeof candidate.value_hypothesis === "string" &&
    typeof candidate.discovery_query === "string" &&
    Array.isArray(candidate.qualification_signals)
  );
}

function ensureHumanApprovalConstraint(constraints: string[]) {
  const approvalConstraint = "Human approval required before outbound messages are sent.";
  if (constraints.some((constraint) => constraint.toLowerCase().includes("human approval"))) {
    return constraints;
  }
  return [...constraints, approvalConstraint];
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
