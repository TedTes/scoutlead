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
  const { selectedProduct, createProductFromSource } = useAppData();
  const [source, setSource] = useState("");
  const [creating, setCreating] = useState(false);
  const showSourceCreator = isCreatingProduct || !selectedProduct;
  const canCreate = source.trim().length > 0 && !creating;

  useEffect(() => {
    if (!isCreatingProduct) return;
    setSource("");
  }, [isCreatingProduct, newProductToken]);

  const submit = async () => {
    if (!canCreate) return;
    setCreating(true);
    try {
      const created = await createProductFromSource({
        source: source.trim(),
        target_geography: "United States",
      });
      if (created) {
        setSource("");
        onCreatingProductChange(false);
      }
    } finally {
      setCreating(false);
    }
  };

  if (showSourceCreator) {
    return (
      <Card title="New product" meta={<StatusPill tone="blue">Draft</StatusPill>}>
        <div className="source-create">
          <label className="field">
            <span>Landing page or source</span>
            <input
              autoFocus
              placeholder="https://quotevan.com or residential painters in Texas"
              value={source}
              onChange={(event) => setSource(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void submit();
              }}
            />
          </label>
          <button disabled={!canCreate} onClick={submit}>
            {creating ? "Creating..." : "Create product"}
          </button>
        </div>
      </Card>
    );
  }

  return (
    <div className="product-summary-grid">
      <Card title={selectedProduct.product_name} meta={<StatusPill tone="green">Active</StatusPill>}>
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
