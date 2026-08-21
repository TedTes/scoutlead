import { Play, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, Modal, useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { Product } from "../types/domain";
import type { Screen } from "../types/navigation";

type ProductScreenProps = {
  isCreatingProduct: boolean;
  onCreatingProductChange: (isCreating: boolean) => void;
  onNavigate: (screen: Screen) => void;
};

export function ProductScreen({
  isCreatingProduct,
  onCreatingProductChange,
  onNavigate,
}: ProductScreenProps) {
  const {
    products,
    selectedProductId,
    setSelectedProductId,
    createProductFromDescription,
    deleteProduct,
    discoverProduct,
  } = useAppData();
  const { showToast } = useToast();
  const [detailProductId, setDetailProductId] = useState("");
  const [productName, setProductName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [localError, setLocalError] = useState("");
  const detailProduct = products.find((product) => product.id === detailProductId);
  const normalizedProductName = productName.trim().toLowerCase();
  const hasDuplicateProductName =
    normalizedProductName.length > 0 &&
    products.some((product) => product.product_name.trim().toLowerCase() === normalizedProductName);
  const canCreateProduct =
    productName.trim().length > 0 &&
    description.trim().length >= 20 &&
    !hasDuplicateProductName &&
    !creating;

  useEffect(() => {
    if (!isCreatingProduct) return;
    setProductName("");
    setDescription("");
    setLocalError("");
  }, [isCreatingProduct]);

  const startCreatingProduct = () => {
    setProductName("");
    setDescription("");
    setLocalError("");
    onCreatingProductChange(true);
  };

  const selectProduct = (product: Product) => {
    setSelectedProductId(product.id);
    setDetailProductId(product.id);
    onCreatingProductChange(false);
    setLocalError("");
  };

  const createFromDescription = async () => {
    if (!canCreateProduct) return;
    setCreating(true);
    setLocalError("");
    try {
      const created = await createProductFromDescription({
        product_name: productName.trim(),
        description: description.trim(),
      });
      if (!created) {
        showToast({ title: "Product was not created", message: "Check the product details and try again.", tone: "red" });
        return;
      }
      setProductName("");
      setDescription("");
      onCreatingProductChange(false);
      setSelectedProductId(created.id);
      setDetailProductId(created.id);
      showToast({
        title: "Product created",
        message: "Use the product description as the discovery context.",
        tone: "green",
      });
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
    const confirmed = window.confirm(
      `Delete ${displayProductName(detailProduct)}? This also removes related discovery results, drafts, and run records for this product.`,
    );
    if (!confirmed) return;
    await deleteProduct(detailProduct.id);
    setDetailProductId("");
    showToast({ title: "Product deleted", message: `${displayProductName(detailProduct)} was removed.`, tone: "green" });
  };

  const startDiscovery = async () => {
    if (!detailProduct || discovering) return;
    setDiscovering(true);
    try {
      await discoverProduct(detailProduct.id, 10);
      showToast({
        title: "Discovery complete",
        message: "Review the results and approval queue.",
        tone: "green",
      });
      onNavigate("results");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Discovery failed", message, tone: "red" });
    } finally {
      setDiscovering(false);
    }
  };

  return (
    <div className="product-page">
      {isCreatingProduct ? (
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
              {hasDuplicateProductName ? <em>A product with this name already exists.</em> : null}
            </label>
            <label className="field">
              <span>Product description</span>
              <textarea
                placeholder="Describe what the product does, who it is for, and where to search if that matters."
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
              <button disabled={!canCreateProduct} type="submit">
                {creating ? "Creating..." : "Create product"}
              </button>
            </div>
          </form>

          {localError ? <p className="form-error">{localError}</p> : null}
        </Modal>
      ) : null}

      {!detailProduct ? (
        <Card
          title="Products"
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
            {products.length ? (
              products.map((product) => (
                <button
                  className={product.id === selectedProductId ? "product-table-row active" : "product-table-row"}
                  key={product.id}
                  type="button"
                  onClick={() => selectProduct(product)}
                >
                  <strong>{displayProductName(product)}</strong>
                  <span>{product.product_description || "No description saved."}</span>
                </button>
              ))
            ) : (
              <p className="empty-copy">No products yet. Add one product name and description to start.</p>
            )}
          </div>
        </Card>
      ) : (
        <div className="product-detail-stack">
          <Card
            title={displayProductName(detailProduct)}
            meta={
              <div className="card-actions">
                <button className="secondary" type="button" onClick={() => setDetailProductId("")}>
                  Back
                </button>
                <button type="button" onClick={startDiscovery} disabled={discovering}>
                  <Play size={14} />
                  {discovering ? "Finding..." : "Find results"}
                </button>
                <button className="danger" onClick={deleteSelectedProduct}>
                  <Trash2 size={14} />
                  Delete
                </button>
              </div>
            }
          >
            <p className="product-brief">{detailProduct.product_description}</p>
            <div className="product-facts">
              <ProductFact label="Created" value={formatDate(detailProduct.created_at)} />
              <ProductFact label="Updated" value={formatDate(detailProduct.updated_at)} />
              <ProductFact label="Source" value="Product description" />
            </div>
          </Card>

          <Card title="Discovery context">
            <p className="empty-copy">
              ScoutLead will use this product description as the context for discovery sources. Include target customer,
              niche, geography, or source hints directly in the description when you want to narrow the search.
            </p>
          </Card>
        </div>
      )}
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

function displayProductName(product: Product) {
  const savedName = product.product_name.trim();
  return savedName || "Unnamed product";
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
