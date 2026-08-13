import { useEffect, useState } from "react";
import { Card, StatusPill, Subhead } from "../shared-ui";
import { useAppData } from "../state/app-data";

type ProductDraft = {
  product_name: string;
  product_description: string;
  target_customer: string;
  problem_being_solved: string;
  value_proposition: string;
  target_geography: string;
  validation_goal: string;
  outreach_objective: string;
  qualification_criteria_text: string;
  discovery_sources_text: string;
  constraints_text: string;
};

const emptyDraft: ProductDraft = {
  product_name: "",
  product_description: "",
  target_customer: "",
  problem_being_solved: "",
  value_proposition: "",
  target_geography: "",
  validation_goal: "",
  outreach_objective: "",
  qualification_criteria_text: "",
  discovery_sources_text: "",
  constraints_text: "",
};

const newProductDraft: ProductDraft = {
  product_name: "",
  product_description: "",
  target_customer: "",
  problem_being_solved: "",
  value_proposition: "",
  target_geography: "",
  validation_goal: "",
  outreach_objective: "",
  qualification_criteria_text: "",
  discovery_sources_text: "",
  constraints_text: "",
};

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
  const { selectedProduct, createProduct, updateSelectedProduct } = useAppData();
  const [draft, setDraft] = useState<ProductDraft>(emptyDraft);

  useEffect(() => {
    if (!isCreatingProduct) return;
    setDraft(newProductDraft);
  }, [isCreatingProduct, newProductToken]);

  useEffect(() => {
    if (isCreatingProduct) return;
    if (!selectedProduct) {
      setDraft(emptyDraft);
      return;
    }
    setDraft({
      product_name: selectedProduct.product_name,
      product_description: selectedProduct.product_description,
      target_customer: selectedProduct.target_customer,
      problem_being_solved: selectedProduct.problem_being_solved,
      value_proposition: selectedProduct.value_proposition,
      target_geography: selectedProduct.target_geography,
      validation_goal: selectedProduct.validation_goal,
      outreach_objective: selectedProduct.outreach_objective,
      qualification_criteria_text: selectedProduct.qualification_criteria
        .map((criterion) => criterion.label)
        .join("\n"),
      discovery_sources_text: selectedProduct.preferred_discovery_sources
        .map((source) => source.value)
        .join("\n"),
      constraints_text: selectedProduct.constraints.join("\n"),
    });
  }, [isCreatingProduct, selectedProduct]);

  const updateDraft = (field: keyof ProductDraft, value: string) => {
    setDraft((current) => ({ ...current, [field]: value }));
  };

  const saveProduct = async () => {
    const payload = buildProductPayload(draft);
    if (isCreatingProduct) {
      const created = await createProduct(payload);
      if (created) onCreatingProductChange(false);
      return;
    }
    await updateSelectedProduct(payload);
  };

  const showEditor = isCreatingProduct || selectedProduct;
  const canSaveProduct =
    draft.product_name.trim().length > 0 &&
    draft.product_description.trim().length > 0 &&
    draft.target_customer.trim().length > 0 &&
    draft.problem_being_solved.trim().length > 0 &&
    draft.value_proposition.trim().length > 0 &&
    draft.target_geography.trim().length > 0 &&
    draft.validation_goal.trim().length > 0 &&
    draft.outreach_objective.trim().length > 0 &&
    toLines(draft.qualification_criteria_text).length > 0 &&
    toLines(draft.discovery_sources_text).length > 0;

  return (
    <>
      {!showEditor ? (
        <Card title="No product selected">
          <p className="empty-copy">Create a product to define discovery context and qualification rules.</p>
        </Card>
      ) : (
        <div className="product-grid">
          <Card
            title={isCreatingProduct ? "New product" : "Product"}
            meta={
              isCreatingProduct ? (
                <StatusPill tone="blue">Draft</StatusPill>
              ) : (
                <StatusPill tone="green">Active</StatusPill>
              )
            }
          >
            <div className="form-grid two">
              <TextField
                label="Product name"
                value={draft.product_name}
                onChange={(value) => updateDraft("product_name", value)}
              />
              <TextField
                label="Target geography"
                value={draft.target_geography}
                onChange={(value) => updateDraft("target_geography", value)}
              />
            </div>
            <TextField
              label="One-line value prop"
              value={draft.value_proposition}
              onChange={(value) => updateDraft("value_proposition", value)}
            />
            <TextField
              label="Product description"
              area
              value={draft.product_description}
              onChange={(value) => updateDraft("product_description", value)}
            />
            <TextField
              label="Problem it solves"
              area
              value={draft.problem_being_solved}
              onChange={(value) => updateDraft("problem_being_solved", value)}
            />
            <TextField
              label="Validation goal"
              value={draft.validation_goal}
              onChange={(value) => updateDraft("validation_goal", value)}
            />
            <TextField
              label="Outreach objective"
              value={draft.outreach_objective}
              onChange={(value) => updateDraft("outreach_objective", value)}
            />
            {!canSaveProduct ? (
              <p className="field-help product-form-help">
                Complete product fields, qualification criteria, and discovery sources to save.
              </p>
            ) : null}
            <div className="form-actions">
              <button disabled={!canSaveProduct} onClick={saveProduct}>
                {isCreatingProduct ? "Create product" : "Save"}
              </button>
            </div>
          </Card>

          <Card title="Ideal customer profile">
            <Subhead>Target customer</Subhead>
            <TextField
              label="Customer profile"
              value={draft.target_customer}
              onChange={(value) => updateDraft("target_customer", value)}
            />

            <Subhead>Qualification criteria</Subhead>
            <TextField
              label="One criterion per line"
              area
              value={draft.qualification_criteria_text}
              onChange={(value) => updateDraft("qualification_criteria_text", value)}
            />

            <Subhead>Discovery sources</Subhead>
            <TextField
              label="One source or search query per line"
              area
              value={draft.discovery_sources_text}
              onChange={(value) => updateDraft("discovery_sources_text", value)}
            />

            <Subhead>Constraints</Subhead>
            <TextField
              label="One constraint per line"
              area
              value={draft.constraints_text}
              onChange={(value) => updateDraft("constraints_text", value)}
            />
          </Card>
        </div>
      )}
    </>
  );
}

function buildProductPayload(draft: ProductDraft) {
  return {
    product_name: draft.product_name.trim(),
    product_description: draft.product_description.trim(),
    target_customer: draft.target_customer.trim(),
    problem_being_solved: draft.problem_being_solved.trim(),
    value_proposition: draft.value_proposition.trim(),
    target_geography: draft.target_geography.trim(),
    validation_goal: draft.validation_goal.trim(),
    outreach_objective: draft.outreach_objective.trim(),
    qualification_criteria: toLines(draft.qualification_criteria_text).map((label) => ({
      label,
      weight: 1,
      required: false,
      evidence_required: true,
    })),
    preferred_discovery_sources: toLines(draft.discovery_sources_text).map((value) => ({
      type: "web_search" as const,
      value,
    })),
    constraints: toLines(draft.constraints_text),
  };
}

function toLines(value: string) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function TextField({
  label,
  value,
  onChange,
  area,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  area?: boolean;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {area ? (
        <textarea value={value} rows={4} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <input value={value} onChange={(event) => onChange(event.target.value)} />
      )}
    </label>
  );
}
