import { ArrowLeft, MapPin, Plus, Target, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { Product } from "../types/domain";
import type { Screen } from "../types/navigation";
import { formatDate } from "../utils/format";

type ProductScreenProps = {
  isCreatingProduct: boolean;
  onCreatingProductChange: (isCreating: boolean) => void;
  onDeleteProduct?: () => Promise<void> | void;
  onNavigate: (screen: Screen) => void;
};

type FocusHintChip =
  | { id: "geography"; label: string; kind: "geography" }
  | { id: `constraint-${number}`; label: string; kind: "constraint"; index: number };

const DEFAULT_TARGET_GEOGRAPHY = "United States, Canada";
const HUMAN_APPROVAL_CONSTRAINT = "human approval required before outbound messages are sent";

export function ProductScreen({
  onCreatingProductChange,
  onDeleteProduct,
  onNavigate,
}: ProductScreenProps) {
  const {
    products,
    selectedProduct,
    selectedProductId,
    productContacts,
    productDiscoveryRuns,
    autoSaveProduct,
  } = useAppData();
  const { showToast } = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [targetGeography, setTargetGeography] = useState(DEFAULT_TARGET_GEOGRAPHY);
  const [constraints, setConstraints] = useState<string[]>([]);
  const [addingHint, setAddingHint] = useState(false);
  const [hintDraft, setHintDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const originalEditableConstraints = useMemo(
    () => editableConstraints(selectedProduct),
    [selectedProduct],
  );

  const hiddenConstraints = useMemo(
    () => hiddenProductConstraints(selectedProduct),
    [selectedProduct],
  );

  useEffect(() => {
    setName(selectedProduct?.product_name || "");
    setDescription(selectedProduct?.product_description || "");
    setTargetGeography(selectedProduct?.target_geography || DEFAULT_TARGET_GEOGRAPHY);
    setConstraints(editableConstraints(selectedProduct));
    setAddingHint(false);
    setHintDraft("");
  }, [selectedProduct]);

  const duplicateName = useMemo(() => {
    const normalized = name.trim().toLowerCase();
    return Boolean(
      normalized &&
        products.some(
          (product) =>
            product.id !== selectedProductId &&
            product.product_name.trim().toLowerCase() === normalized,
        ),
    );
  }, [name, products, selectedProductId]);

  const normalizedConstraints = useMemo(() => normalizeList(constraints), [constraints]);
  const hasChanges = Boolean(
    selectedProduct &&
      (name.trim() !== selectedProduct.product_name.trim() ||
        description.trim() !== selectedProduct.product_description.trim() ||
        targetGeography.trim() !== selectedProduct.target_geography.trim() ||
        !sameList(normalizedConstraints, originalEditableConstraints)),
  );
  const canAutosave = Boolean(
    selectedProduct &&
      name.trim() &&
      description.trim().length >= 20 &&
      targetGeography.trim() &&
      hasChanges &&
      !duplicateName &&
      !saving,
  );
  const focusHintChips = useMemo(
    () => buildFocusHintChips(targetGeography, normalizedConstraints),
    [normalizedConstraints, targetGeography],
  );

  const addHint = () => {
    const normalized = hintDraft.trim();
    if (!normalized) return;
    setConstraints((current) => normalizeList([...current, normalized]));
    setHintDraft("");
    setAddingHint(false);
  };

  const removeHint = (chip: FocusHintChip) => {
    if (chip.kind === "geography") {
      setTargetGeography(DEFAULT_TARGET_GEOGRAPHY);
      return;
    }
    setConstraints((current) => current.filter((_, index) => index !== chip.index));
  };

  const confirmDeleteProduct = async () => {
    if (!selectedProduct || !onDeleteProduct || deleting) return;
    setDeleting(true);
    try {
      await onDeleteProduct();
      setConfirmingDelete(false);
    } finally {
      setDeleting(false);
    }
  };

  const saveProduct = useCallback(async () => {
    if (!selectedProduct || !canAutosave) return;
    setSaving(true);
    try {
      await autoSaveProduct(selectedProduct.id, {
        product_name: name.trim(),
        product_description: description.trim(),
        target_geography: targetGeography.trim(),
        constraints: normalizeList([...hiddenConstraints, ...normalizedConstraints]),
      });
    } catch (error) {
      showToast({
        title: "Product changes were not saved",
        message: error instanceof Error ? error.message : String(error),
        tone: "red",
      });
    } finally {
      setSaving(false);
    }
  }, [
    autoSaveProduct,
    canAutosave,
    description,
    hiddenConstraints,
    name,
    normalizedConstraints,
    selectedProduct,
    showToast,
    targetGeography,
  ]);

  useEffect(() => {
    if (!canAutosave) return;
    const timeout = window.setTimeout(() => {
      void saveProduct();
    }, 750);
    return () => window.clearTimeout(timeout);
  }, [canAutosave, saveProduct]);

  if (!selectedProduct) {
    return (
      <div className="product-page product-settings-page">
        <section className="product-settings-empty">
          <h1>No product selected</h1>
          <p>Create a product from the top bar before changing product settings.</p>
          <button className="runbtn" type="button" onClick={() => onCreatingProductChange(true)}>
            Add product
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="product-page product-settings-page">
      <section className="product-settings-shell">
        <header className="product-settings-heading">
          <div className="product-settings-meta-line" aria-label="Product summary">
            <span>
              <strong>{productDiscoveryRuns.length}</strong> {pluralize(productDiscoveryRuns.length, "run")}
            </span>
            <span>
              <strong>{productContacts.length}</strong> {pluralize(productContacts.length, "contact")}
            </span>
            <span>
              updated <strong>{formatDate(selectedProduct.updated_at)}</strong>
            </span>
          </div>
          <button className="secondary product-settings-finder" type="button" onClick={() => onNavigate("overview")}>
            <ArrowLeft size={15} />
            Finder
          </button>
        </header>

        <form
          className="product-settings-form"
          onSubmit={(event) => {
            event.preventDefault();
            void saveProduct();
          }}
        >
          <label className="product-settings-field">
            <span className="product-settings-label">Product name</span>
            <input
              className="product-settings-input"
              value={name}
              onChange={(event) => setName(event.target.value)}
              onBlur={() => void saveProduct()}
            />
            {duplicateName ? <em>A product with this name already exists.</em> : null}
          </label>

          <label className="product-settings-field">
            <span className="product-settings-label">Product description</span>
            <textarea
              className="product-settings-textarea"
              rows={7}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              onBlur={() => void saveProduct()}
            />
            <span className="product-settings-count">{description.length} chars</span>
            <small className="product-settings-copy-hint">
              This is what the finder scores against. Describe what it does, who it helps, and any market or geography
              hints. The more specific, the sharper the fit scoring.
            </small>
          </label>

          <section className="product-settings-field" aria-label="Focus hints">
            <div className="product-settings-focus-head">
              <span className="product-settings-label">Focus hints</span>
              <span>optional</span>
            </div>
            <div className="product-settings-chip-list">
              {focusHintChips.map((chip) => (
                <span className="product-settings-chip" key={chip.id}>
                  {chip.kind === "geography" ? <MapPin size={13} /> : <Target size={13} />}
                  <span className="product-settings-chip-text">{chip.label}</span>
                  <button
                    className="product-settings-chip-remove"
                    type="button"
                    aria-label={`Remove ${chip.label}`}
                    onClick={() => removeHint(chip)}
                  >
                    <X size={13} />
                  </button>
                </span>
              ))}
              <button
                className="product-settings-chip product-settings-chip-add"
                type="button"
                onClick={() => setAddingHint(true)}
              >
                <Plus size={13} />
                add hint
              </button>
            </div>
            {addingHint ? (
              <div className="product-settings-hint-editor">
                <input
                  autoFocus
                  placeholder="e.g. owner-operated crews"
                  value={hintDraft}
                  onChange={(event) => setHintDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      addHint();
                    }
                    if (event.key === "Escape") {
                      setAddingHint(false);
                      setHintDraft("");
                    }
                  }}
                />
                <button className="secondary" type="button" onClick={addHint}>
                  Add
                </button>
              </div>
            ) : null}
            <small className="product-settings-copy-hint">
              Optional structured hints the finder weights alongside the description.
            </small>
          </section>

          <section className="product-settings-danger" aria-label="Danger zone">
            <div>
              <span className="product-settings-danger-label">Danger zone</span>
              <p>Delete this product and remove its runs, contacts, and history.</p>
            </div>
            {confirmingDelete ? (
              <div className="product-settings-delete-confirm">
                <span>Delete this product?</span>
                <button className="secondary" type="button" onClick={() => setConfirmingDelete(false)}>
                  Cancel
                </button>
                <button
                  className="product-settings-delete-button"
                  disabled={deleting}
                  type="button"
                  onClick={() => void confirmDeleteProduct()}
                >
                  {deleting ? "Deleting..." : "Delete"}
                </button>
              </div>
            ) : (
              <button
                className="product-settings-delete-button"
                disabled={!onDeleteProduct}
                type="button"
                onClick={() => setConfirmingDelete(true)}
              >
                <Trash2 size={14} />
                Delete product
              </button>
            )}
          </section>
        </form>
      </section>
    </div>
  );
}

function buildFocusHintChips(
  targetGeography: string,
  constraints: string[],
): FocusHintChip[] {
  const chips: FocusHintChip[] = [];
  const geography = targetGeography.trim();
  if (geography && geography !== DEFAULT_TARGET_GEOGRAPHY) {
    chips.push({ id: "geography", label: geography, kind: "geography" });
  }
  constraints.forEach((constraint, index) => {
    chips.push({ id: `constraint-${index}`, label: constraint, kind: "constraint", index });
  });
  return chips;
}

function editableConstraints(product: Product | undefined) {
  return normalizeList((product?.constraints || []).filter((constraint) => !isHiddenConstraint(constraint)));
}

function hiddenProductConstraints(product: Product | undefined) {
  return normalizeList((product?.constraints || []).filter(isHiddenConstraint));
}

function isHiddenConstraint(value: string) {
  return value.toLowerCase().includes(HUMAN_APPROVAL_CONSTRAINT);
}

function normalizeList(values: string[]) {
  const seen = new Set<string>();
  return values
    .map((value) => value.trim())
    .filter(Boolean)
    .filter((value) => {
      const key = value.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function sameList(first: string[], second: string[]) {
  if (first.length !== second.length) return false;
  return first.every((value, index) => value === second[index]);
}

function pluralize(count: number, singular: string) {
  return count === 1 ? singular : `${singular}s`;
}
