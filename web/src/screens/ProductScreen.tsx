import { ArrowLeft, CircleOff, Plus, Target, Trash2, X } from "lucide-react";
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

const DEFAULT_TARGET_GEOGRAPHY = "United States, Canada";

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
  const [offerSummary, setOfferSummary] = useState("");
  const [targetCustomer, setTargetCustomer] = useState("");
  const [targetGeography, setTargetGeography] = useState(DEFAULT_TARGET_GEOGRAPHY);
  const [idealCustomerSignals, setIdealCustomerSignals] = useState<string[]>([]);
  const [exclusions, setExclusions] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const draft = productProfileDraft(selectedProduct);
    setName(selectedProduct?.product_name || "");
    setOfferSummary(draft.offerSummary);
    setTargetCustomer(draft.targetCustomer);
    setTargetGeography(selectedProduct?.target_geography || DEFAULT_TARGET_GEOGRAPHY);
    setIdealCustomerSignals(draft.idealCustomerSignals);
    setExclusions(draft.exclusions);
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

  const normalizedSignals = useMemo(() => normalizeList(idealCustomerSignals), [idealCustomerSignals]);
  const normalizedExclusions = useMemo(() => normalizeList(exclusions), [exclusions]);
  const hasChanges = Boolean(
    selectedProduct &&
      (name.trim() !== selectedProduct.product_name.trim() ||
        offerSummary.trim() !== (selectedProduct.offer_summary || selectedProduct.product_description || "").trim() ||
        targetCustomer.trim() !== selectedProduct.target_customer.trim() ||
        targetGeography.trim() !== selectedProduct.target_geography.trim() ||
        !sameList(normalizedSignals, normalizeList(selectedProduct.ideal_customer_signals || [])) ||
        !sameList(normalizedExclusions, normalizeList(selectedProduct.exclusions || []))),
  );
  const canAutosave = Boolean(
    selectedProduct &&
      name.trim() &&
      offerSummary.trim().length >= 20 &&
      targetCustomer.trim() &&
      targetGeography.trim() &&
      hasChanges &&
      !duplicateName &&
      !saving,
  );

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
        offer_summary: offerSummary.trim(),
        target_customer: targetCustomer.trim(),
        target_geography: targetGeography.trim(),
        ideal_customer_signals: normalizedSignals,
        exclusions: normalizedExclusions,
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
    exclusions,
    idealCustomerSignals,
    name,
    normalizedExclusions,
    normalizedSignals,
    offerSummary,
    selectedProduct,
    showToast,
    targetCustomer,
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
          <p>Create a product profile before configuring lead discovery.</p>
          <button className="runbtn" type="button" onClick={() => onCreatingProductChange(true)}>
            <Plus size={15} />
            New product
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="product-page product-settings-page">
      <section className="product-settings-shell">
        <header className="product-settings-heading">
          <div className="product-settings-title-block">
            <h1>Product profile</h1>
            <div className="product-settings-meta-line" aria-label="Product summary">
              <span>
                <strong>{productDiscoveryRuns.length}</strong> {pluralize(productDiscoveryRuns.length, "run")}
              </span>
              <span>
                <strong>{productContacts.length}</strong> {pluralize(productContacts.length, "contact")}
              </span>
              <span>
                {saving ? "saving changes" : <>updated <strong>{formatDate(selectedProduct.updated_at)}</strong></>}
              </span>
            </div>
          </div>
          <div className="product-settings-actions">
            <button
              className="secondary product-settings-new"
              type="button"
              onClick={() => onCreatingProductChange(true)}
            >
              <Plus size={15} />
              New product
            </button>
            <button className="secondary product-settings-finder" type="button" onClick={() => onNavigate("overview")}>
              <ArrowLeft size={15} />
              Finder
            </button>
          </div>
        </header>

        <form
          className="product-settings-form"
          onSubmit={(event) => {
            event.preventDefault();
            void saveProduct();
          }}
        >
          <section className="product-profile-section" aria-labelledby="product-profile-offer">
            <header className="product-profile-section-heading">
              <span>01</span>
              <div>
                <h2 id="product-profile-offer">Your product</h2>
                <p>Name the offer and describe the outcome you provide.</p>
              </div>
            </header>
            <div className="product-profile-section-fields">
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
                <span className="product-settings-label">What you sell</span>
                <textarea
                  className="product-settings-textarea is-compact"
                  rows={3}
                  value={offerSummary}
                  onChange={(event) => setOfferSummary(event.target.value)}
                  onBlur={() => void saveProduct()}
                />
                <small className="product-settings-copy-hint">
                  State the service and the practical result a customer receives.
                </small>
              </label>
            </div>
          </section>

          <section className="product-profile-section" aria-labelledby="product-profile-market">
            <header className="product-profile-section-heading">
              <span>02</span>
              <div>
                <h2 id="product-profile-market">Businesses to find</h2>
                <p>Define the companies that should appear in your lead lists.</p>
              </div>
            </header>
            <div className="product-profile-section-fields">
              <label className="product-settings-field">
                <span className="product-settings-label">Target customer</span>
                <textarea
                  className="product-settings-textarea is-compact"
                  rows={3}
                  value={targetCustomer}
                  onChange={(event) => setTargetCustomer(event.target.value)}
                  onBlur={() => void saveProduct()}
                />
                <small className="product-settings-copy-hint">
                  Describe the business type, not the people you plan to contact.
                </small>
              </label>

              <label className="product-settings-field">
                <span className="product-settings-label">Geography</span>
                <input
                  className="product-settings-input"
                  value={targetGeography}
                  onChange={(event) => setTargetGeography(event.target.value)}
                  onBlur={() => void saveProduct()}
                />
              </label>
            </div>
          </section>

          <section className="product-profile-section" aria-labelledby="product-profile-qualification">
            <header className="product-profile-section-heading">
              <span>03</span>
              <div>
                <h2 id="product-profile-qualification">Qualification</h2>
                <p>Tell the finder what evidence makes a business useful or irrelevant.</p>
              </div>
            </header>
            <div className="product-profile-section-fields">
              <ProfileListEditor
                kind="signal"
                label="Opportunity signals"
                placeholder="e.g. no quote form"
                values={idealCustomerSignals}
                onChange={setIdealCustomerSignals}
              />
              <ProfileListEditor
                kind="exclusion"
                label="Exclude"
                placeholder="e.g. national chains"
                values={exclusions}
                onChange={setExclusions}
              />
            </div>
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

function productProfileDraft(product: Product | undefined) {
  if (!product) {
    return {
      offerSummary: "",
      targetCustomer: "",
      idealCustomerSignals: [] as string[],
      exclusions: [] as string[],
    };
  }

  const rawSummary = (product.offer_summary || product.product_description || "").trim();
  const labeled = parseLabeledProductSummary(rawSummary);
  const savedTarget = product.target_customer.trim();
  return {
    offerSummary: labeled.offer || rawSummary,
    targetCustomer:
      labeled.targetCustomer || (/^define target customer/i.test(savedTarget) ? "" : savedTarget),
    idealCustomerSignals: normalizeList(
      product.ideal_customer_signals.length
        ? product.ideal_customer_signals
        : splitProfileList(labeled.positiveSignals),
    ),
    exclusions: normalizeList(
      product.exclusions.length ? product.exclusions : splitProfileList(labeled.disqualifiers),
    ),
  };
}

function parseLabeledProductSummary(value: string) {
  const fields: Record<string, string> = {};
  const labels = /(?:^|\s)(Offer|Target customer|Problem solved|Positive signals|Disqualifiers):\s*/gi;
  const matches = [...value.matchAll(labels)];
  matches.forEach((match, index) => {
    const label = match[1].toLowerCase();
    const start = (match.index || 0) + match[0].length;
    const end = matches[index + 1]?.index ?? value.length;
    fields[label] = value.slice(start, end).trim().replace(/[.;]$/, "");
  });
  return {
    offer: fields.offer || "",
    targetCustomer: fields["target customer"] || "",
    positiveSignals: fields["positive signals"] || "",
    disqualifiers: fields.disqualifiers || "",
  };
}

function splitProfileList(value: string) {
  return value ? value.replace(/,\s*and\s+/gi, ", ").split(/[,;]\s*/) : [];
}

function ProfileListEditor({
  kind,
  label,
  onChange,
  placeholder,
  values,
}: {
  kind: "signal" | "exclusion";
  label: string;
  onChange: (values: string[]) => void;
  placeholder: string;
  values: string[];
}) {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const Icon = kind === "signal" ? Target : CircleOff;

  const addValue = () => {
    const normalized = draft.trim();
    if (!normalized) return;
    onChange(normalizeList([...values, normalized]));
    setDraft("");
    setAdding(false);
  };

  return (
    <div className="product-settings-field product-profile-list-field">
      <span className="product-settings-label">{label}</span>
      <div className="product-settings-chip-list">
        {values.map((value, index) => (
          <span className={`product-settings-chip is-${kind}`} key={`${value}-${index}`}>
            <Icon size={13} />
            <span className="product-settings-chip-text">{value}</span>
            <button
              aria-label={`Remove ${value}`}
              className="product-settings-chip-remove"
              type="button"
              onClick={() => onChange(values.filter((_, valueIndex) => valueIndex !== index))}
            >
              <X size={13} />
            </button>
          </span>
        ))}
        {!adding ? (
          <button
            className="product-settings-chip product-settings-chip-add"
            type="button"
            onClick={() => setAdding(true)}
          >
            <Plus size={13} />
            Add
          </button>
        ) : null}
      </div>
      {adding ? (
        <div className="product-settings-hint-editor">
          <input
            autoFocus
            placeholder={placeholder}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addValue();
              }
              if (event.key === "Escape") {
                setAdding(false);
                setDraft("");
              }
            }}
          />
          <button className="secondary" type="button" onClick={addValue}>
            Add
          </button>
          <button
            aria-label="Cancel"
            className="product-profile-list-cancel"
            type="button"
            onClick={() => {
              setAdding(false);
              setDraft("");
            }}
          >
            <X size={14} />
          </button>
        </div>
      ) : null}
    </div>
  );
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
