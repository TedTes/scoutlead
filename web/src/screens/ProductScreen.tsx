import { ArrowLeft, Mail, PlugZap, Save, Unplug } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { Screen } from "../types/navigation";
import { formatDate } from "../utils/format";

type ProductScreenProps = {
  isCreatingProduct: boolean;
  onCreatingProductChange: (isCreating: boolean) => void;
  onNavigate: (screen: Screen) => void;
};

export function ProductScreen({
  onCreatingProductChange,
  onNavigate,
}: ProductScreenProps) {
  const {
    products,
    selectedProduct,
    selectedProductId,
    productContacts,
    productDiscoveryRuns,
    gmailConnectionStatus,
    getGmailAuthorizationUrl,
    refreshGmailConnection,
    disconnectGmail,
    updateProduct,
  } = useAppData();
  const { showToast } = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookEnabled, setWebhookEnabled] = useState(false);
  const [saving, setSaving] = useState(false);
  const [connectingGmail, setConnectingGmail] = useState(false);
  const [disconnectingGmail, setDisconnectingGmail] = useState(false);

  useEffect(() => {
    setName(selectedProduct?.product_name || "");
    setDescription(selectedProduct?.product_description || "");
    setWebhookUrl(selectedProduct?.webhook_url || "");
    setWebhookEnabled(Boolean(selectedProduct?.webhook_enabled));
  }, [
    selectedProduct?.id,
    selectedProduct?.product_description,
    selectedProduct?.product_name,
    selectedProduct?.webhook_enabled,
    selectedProduct?.webhook_url,
  ]);

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

  const hasChanges = Boolean(
    selectedProduct &&
      (name.trim() !== selectedProduct.product_name.trim() ||
        description.trim() !== selectedProduct.product_description.trim() ||
        webhookUrl.trim() !== (selectedProduct.webhook_url || "").trim() ||
        webhookEnabled !== Boolean(selectedProduct.webhook_enabled)),
  );
  const webhookUrlValid = !webhookUrl.trim() || /^https?:\/\//i.test(webhookUrl.trim());
  const canSave = Boolean(
    selectedProduct &&
      name.trim() &&
      description.trim().length >= 20 &&
      webhookUrlValid &&
      hasChanges &&
      !duplicateName &&
      !saving,
  );

  const saveProduct = async () => {
    if (!selectedProduct || !canSave) return;
    setSaving(true);
    try {
      await updateProduct(selectedProduct.id, {
        product_name: name.trim(),
        product_description: description.trim(),
        webhook_url: webhookUrl.trim() || null,
        webhook_enabled: Boolean(webhookEnabled && webhookUrl.trim()),
      });
      showToast({ title: "Product saved", message: "Discovery will use the updated context.", tone: "green" });
    } catch (error) {
      showToast({
        title: "Product was not saved",
        message: error instanceof Error ? error.message : String(error),
        tone: "red",
      });
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    const handleGmailMessage = (event: MessageEvent) => {
      if (event.data?.type === "scoutlead:gmail:connected" || event.data?.type === "scoutlead:gmail:failed") {
        void refreshGmailConnection(selectedProductId);
      }
    };
    window.addEventListener("message", handleGmailMessage);
    return () => window.removeEventListener("message", handleGmailMessage);
  }, [refreshGmailConnection, selectedProductId]);

  const connectGmail = async () => {
    if (!selectedProduct || connectingGmail) return;
    setConnectingGmail(true);
    try {
      const response = await getGmailAuthorizationUrl(selectedProduct.id);
      if (!response?.authorization_url) return;
      const popup = window.open(
        response.authorization_url,
        "scoutlead-gmail-connect",
        "popup,width=520,height=720",
      );
      if (!popup) {
        window.location.href = response.authorization_url;
      }
      window.setTimeout(() => void refreshGmailConnection(selectedProduct.id), 1200);
    } catch (error) {
      showToast({
        title: "Gmail connection failed",
        message: error instanceof Error ? error.message : String(error),
        tone: "red",
      });
    } finally {
      setConnectingGmail(false);
    }
  };

  const disconnectProductGmail = async () => {
    if (!selectedProduct || disconnectingGmail) return;
    setDisconnectingGmail(true);
    try {
      await disconnectGmail(selectedProduct.id);
      showToast({ title: "Gmail disconnected", message: "This product will not send through Gmail.", tone: "green" });
    } catch (error) {
      showToast({
        title: "Gmail disconnect failed",
        message: error instanceof Error ? error.message : String(error),
        tone: "red",
      });
    } finally {
      setDisconnectingGmail(false);
    }
  };

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
      <section className="product-settings-card">
        <header className="product-settings-header">
          <div>
            <span>Product settings</span>
            <h1>{selectedProduct.product_name}</h1>
          </div>
          <button className="secondary" type="button" onClick={() => onNavigate("overview")}>
            <ArrowLeft size={14} />
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
          <label className="field product-name-field">
            <span>Product name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} />
            {duplicateName ? <em>A product with this name already exists.</em> : null}
          </label>

          <label className="field">
            <span>Product description</span>
            <textarea
              rows={8}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
            <small className="product-settings-hint">
              Describe what it does, who it helps, and any market or geography hints you want the finder to use.
            </small>
          </label>

          <div className="product-settings-meta" aria-label="Product summary">
            <ProductSettingMeta label="Runs" value={String(productDiscoveryRuns.length)} />
            <ProductSettingMeta label="Contacts" value={String(productContacts.length)} />
            <ProductSettingMeta label="Updated" value={formatDate(selectedProduct.updated_at)} />
          </div>

          <section className="product-settings-gmail" aria-label="Gmail sending connection">
            <div className="product-settings-gmail-icon">
              <Mail size={16} />
            </div>
            <div className="product-settings-gmail-copy">
              <span>Gmail sending</span>
              <strong>
                {gmailConnectionStatus?.connected
                  ? gmailConnectionStatus.email_address || "Connected"
                  : "Not connected"}
              </strong>
              {gmailConnectionStatus?.last_error ? <em>{gmailConnectionStatus.last_error}</em> : null}
            </div>
            {gmailConnectionStatus?.connected ? (
              <button
                className="secondary product-settings-gmail-action"
                type="button"
                disabled={disconnectingGmail}
                onClick={() => void disconnectProductGmail()}
              >
                <Unplug size={14} />
                {disconnectingGmail ? "Disconnecting..." : "Disconnect"}
              </button>
            ) : (
              <button
                className="runbtn product-settings-gmail-action"
                type="button"
                disabled={connectingGmail}
                onClick={() => void connectGmail()}
              >
                <PlugZap size={14} />
                {connectingGmail ? "Connecting..." : "Connect Gmail"}
              </button>
            )}
          </section>

          <section className="product-settings-webhook" aria-label="Approved shortlist webhook">
            <div className="product-settings-webhook-copy">
              <span>Approved shortlist webhook</span>
              <strong>{webhookEnabled && webhookUrl.trim() ? "Enabled" : "Off"}</strong>
              <em>Posts approved shortlisted contacts as JSON.</em>
            </div>
            <label className="field product-settings-webhook-url">
              <span>Webhook URL</span>
              <input
                placeholder="https://hooks.example/approved-shortlist"
                value={webhookUrl}
                onChange={(event) => setWebhookUrl(event.target.value)}
              />
              {!webhookUrlValid ? <em>Use a full http or https URL.</em> : null}
            </label>
            <label className="product-settings-webhook-toggle">
              <input
                checked={webhookEnabled}
                disabled={!webhookUrl.trim()}
                type="checkbox"
                onChange={(event) => setWebhookEnabled(event.target.checked)}
              />
              Enable webhook delivery
            </label>
          </section>

          <footer className="product-settings-actions">
            {!hasChanges ? <span>No unsaved changes</span> : <span>Unsaved changes</span>}
            <button className="runbtn" disabled={!canSave} type="submit">
              <Save size={14} />
              {saving ? "Saving..." : "Save"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}

function ProductSettingMeta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
