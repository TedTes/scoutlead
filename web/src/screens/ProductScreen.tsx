import { Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, StatusPill, Subhead } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { ProductInference } from "../types/domain";
import type { Tone } from "../types/navigation";

type ProductScreenProps = {
  isCreatingProduct: boolean;
  newProductToken: number;
  onCreatingProductChange: (isCreating: boolean) => void;
};

export function ProductScreen({
  isCreatingProduct,
  newProductToken,
  onCreatingProductChange,
}: ProductScreenProps) {
  const {
    selectedProduct,
    productCampaigns,
    createProduct,
    deleteProduct,
    inferProductFromSource,
    refreshAll,
    setSelectedProductId,
  } = useAppData();
  const [source, setSource] = useState("");
  const [context, setContext] = useState("");
  const [draft, setDraft] = useState<ProductInference | null>(null);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState("");
  const showSourceCreator = isCreatingProduct || !selectedProduct;
  const canGenerate = source.trim().length > 0 && !generating;
  const canSave = Boolean(draft?.ready_to_save && !saving);

  useEffect(() => {
    if (!isCreatingProduct) return;
    setSource("");
    setContext("");
    setDraft(null);
    setLocalError("");
  }, [isCreatingProduct, newProductToken]);

  const generateDraft = async () => {
    if (!canGenerate) return;
    setGenerating(true);
    setLocalError("");
    try {
      const result = await inferProductFromSource({
        source: source.trim(),
        context: context.trim() || undefined,
        target_geography: "United States",
      });
      if (result.existing_product) {
        window.alert(`${result.existing_product.product_name} already exists. Opening the saved product.`);
        setSelectedProductId(result.existing_product.id);
        await refreshAll();
        setSource("");
        setContext("");
        setDraft(null);
        onCreatingProductChange(false);
        return;
      }
      setDraft(result);
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
    } finally {
      setGenerating(false);
    }
  };

  const saveDraft = async () => {
    if (!draft?.ready_to_save || saving) return;
    setSaving(true);
    setLocalError("");
    try {
      const created = await createProduct(draft.product);
      if (created) {
        setSource("");
        setContext("");
        setDraft(null);
        onCreatingProductChange(false);
      }
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const deleteSelectedProduct = async () => {
    if (!selectedProduct) return;
    const campaignCount = productCampaigns.length;
    const confirmed = window.confirm(
      `Delete ${selectedProduct.product_name}? This also deletes ${campaignCount} related campaign${campaignCount === 1 ? "" : "s"} and all leads, messages, conversations, and agent records for this product.`,
    );
    if (!confirmed) return;
    await deleteProduct(selectedProduct.id);
  };

  if (showSourceCreator) {
    return (
      <Card title="New product" meta={<StatusPill tone="blue">Draft</StatusPill>}>
        <form
          className="source-create product-source-create"
          onSubmit={(event) => {
            event.preventDefault();
            void generateDraft();
          }}
        >
          <label className="field">
            <span>Landing page or source</span>
            <input
              autoFocus
              placeholder="https://quotevan.com"
              value={source}
              onChange={(event) => setSource(event.target.value)}
            />
          </label>
          <button disabled={!canGenerate} type="submit">
            {generating ? "Generating..." : "Generate draft"}
          </button>
        </form>

        {draft && !draft.ready_to_save ? (
          <div className="context-retry">
            <label className="field">
              <span>One-line context</span>
              <input
                placeholder="Example: Quote intake workflow for residential painting companies"
                value={context}
                onChange={(event) => setContext(event.target.value)}
              />
            </label>
            <button disabled={!canGenerate} onClick={generateDraft}>
              Regenerate
            </button>
          </div>
        ) : null}

        {localError ? <p className="form-error">{localError}</p> : null}
        {draft ? (
          <ProductDraftReview
            draft={draft}
            saving={saving}
            canSave={canSave}
            onSave={() => void saveDraft()}
          />
        ) : null}
      </Card>
    );
  }

  return (
    <div className="product-summary-grid">
      <Card
        title={selectedProduct.product_name}
        meta={
          <div className="card-actions">
            <StatusPill tone="green">Active</StatusPill>
            <button className="danger" onClick={deleteSelectedProduct}>
              <Trash2 size={14} />
              Delete
            </button>
          </div>
        }
      >
        <div className="summary-list">
          <SummaryItem label="Target customer" value={selectedProduct.target_customer} />
          <SummaryItem label="Problem" value={selectedProduct.problem_being_solved} />
          <SummaryItem label="Value proposition" value={selectedProduct.value_proposition} />
          <SummaryItem label="Geography" value={selectedProduct.target_geography} />
          <SummaryItem label="Validation goal" value={selectedProduct.validation_goal} />
        </div>
      </Card>

      <Card title="Discovery profile">
        <Subhead>Qualification criteria</Subhead>
        <div className="stacked-chips">
          {selectedProduct.qualification_criteria.map((criterion) => (
            <span className="chip blue" key={criterion.id || criterion.label}>
              {criterion.label}
            </span>
          ))}
        </div>

        <Subhead>Discovery sources</Subhead>
        <div className="summary-list compact">
          {selectedProduct.preferred_discovery_sources.map((discoverySource) => (
            <SummaryItem
              key={`${discoverySource.type}:${discoverySource.value}`}
              label={discoverySource.type}
              value={discoverySource.value}
            />
          ))}
        </div>

        <Subhead>Constraints</Subhead>
        <div className="stacked-chips">
          {selectedProduct.constraints.map((constraint) => (
            <span className="chip grey" key={constraint}>
              {constraint}
            </span>
          ))}
        </div>
      </Card>
    </div>
  );
}

function ProductDraftReview({
  draft,
  saving,
  canSave,
  onSave,
}: {
  draft: ProductInference;
  saving: boolean;
  canSave: boolean;
  onSave: () => void;
}) {
  const product = draft.product;
  const confidenceTone: Tone = draft.confidence >= 75 ? "green" : draft.confidence >= 50 ? "amber" : "red";

  return (
    <div className="product-draft-review">
      <div className="draft-status-row">
        <div>
          <StatusPill tone={confidenceTone}>{draft.confidence}% confidence</StatusPill>
          <p>{draft.evidence.rationale}</p>
        </div>
        <button disabled={!canSave} onClick={onSave}>
          {saving ? "Saving..." : "Save product"}
        </button>
      </div>

      {!draft.ready_to_save ? (
        <div className="draft-warning">
          <strong>More context needed before saving.</strong>
          <ul>
            {draft.missing_info.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="product-draft-grid">
        <div className="summary-list">
          <SummaryItem label="Product" value={product.product_name} />
          <SummaryItem label="Target customer" value={product.target_customer} />
          <SummaryItem label="Problem" value={product.problem_being_solved} />
          <SummaryItem label="Value proposition" value={product.value_proposition} />
          <SummaryItem label="Geography" value={product.target_geography} />
          <SummaryItem label="Validation goal" value={product.validation_goal} />
        </div>

        <div>
          <Subhead>Evidence</Subhead>
          <div className="evidence-list">
            {draft.evidence.source_snippets.length ? (
              draft.evidence.source_snippets.map((snippet) => <p key={snippet}>{snippet}</p>)
            ) : (
              <p>No usable source snippets found.</p>
            )}
          </div>

          <Subhead>Qualification criteria</Subhead>
          <div className="stacked-chips">
            {product.qualification_criteria.map((criterion) => (
              <span className="chip blue" key={criterion.id || criterion.label}>
                {criterion.label}
              </span>
            ))}
          </div>

          <Subhead>Discovery sources</Subhead>
          <div className="summary-list compact">
            {product.preferred_discovery_sources.map((discoverySource) => (
              <SummaryItem
                key={`${discoverySource.type}:${discoverySource.value}`}
                label={discoverySource.type}
                value={discoverySource.value}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
