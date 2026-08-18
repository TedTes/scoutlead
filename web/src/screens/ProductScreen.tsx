import { Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, StatusPill, Subhead } from "../shared-ui";
import { useAppData } from "../state/app-data";

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
    createProductFromDescription,
    deleteProduct,
  } = useAppData();
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [localError, setLocalError] = useState("");
  const showProductCreator = isCreatingProduct || !selectedProduct;
  const canCreate = description.trim().length >= 20 && !creating;

  useEffect(() => {
    if (!isCreatingProduct) return;
    setDescription("");
    setLocalError("");
  }, [isCreatingProduct, newProductToken]);

  const createFromDescription = async () => {
    if (!canCreate) return;
    setCreating(true);
    setLocalError("");
    try {
      const created = await createProductFromDescription({
        description: description.trim(),
        target_geography: "United States",
      });
      if (created) {
        setDescription("");
        onCreatingProductChange(false);
      }
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
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

  if (showProductCreator) {
    return (
      <Card title="New product">
        <form
          className="product-description-create"
          onSubmit={(event) => {
            event.preventDefault();
            void createFromDescription();
          }}
        >
          <label className="field">
            <span>Describe your product</span>
            <textarea
              autoFocus
              placeholder="Example: QuoteVan helps home-service painters capture job scope during a walkthrough, send a professional quote before leaving the job, and keep customer history in one place."
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          <button disabled={!canCreate} type="submit">
            {creating ? "Creating..." : "Create product"}
          </button>
        </form>

        {localError ? <p className="form-error">{localError}</p> : null}
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

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
