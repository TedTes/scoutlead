import {
  AlertTriangle,
  ArrowRight,
  Check,
  Info,
  Link2,
  PlugZap,
  Save,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";

export function IntegrationsScreen() {
  const {
    selectedProduct,
    selectedProductId,
    gmailConnectionStatus,
    getGmailAuthorizationUrl,
    refreshGmailConnection,
    disconnectGmail,
    updateProduct,
  } = useAppData();
  const { showToast } = useToast();
  const [connectingGmail, setConnectingGmail] = useState(false);
  const [disconnectingGmail, setDisconnectingGmail] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookEnabled, setWebhookEnabled] = useState(false);
  const [editingWebhook, setEditingWebhook] = useState(false);
  const [savingWebhook, setSavingWebhook] = useState(false);

  const gmailConnected = Boolean(gmailConnectionStatus?.connected);
  const gmailEmail = gmailConnectionStatus?.email_address || "Connected account";
  const webhookActive = Boolean(selectedProduct?.webhook_enabled && selectedProduct.webhook_url);
  const webhookUrlValid = !webhookUrl.trim() || /^https?:\/\//i.test(webhookUrl.trim());

  useEffect(() => {
    setWebhookUrl(selectedProduct?.webhook_url || "");
    setWebhookEnabled(Boolean(selectedProduct?.webhook_enabled));
    setEditingWebhook(false);
  }, [selectedProduct?.id, selectedProduct?.webhook_enabled, selectedProduct?.webhook_url]);

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
      if (!popup) window.location.href = response.authorization_url;
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

  const saveWebhook = async () => {
    if (!selectedProduct || savingWebhook || !webhookUrlValid) return;
    setSavingWebhook(true);
    try {
      const nextUrl = webhookUrl.trim();
      await updateProduct(selectedProduct.id, {
        webhook_url: nextUrl || null,
        webhook_enabled: Boolean(nextUrl && webhookEnabled),
      });
      setEditingWebhook(false);
      showToast({ title: "Webhook saved", message: "Approved shortlist delivery settings were updated.", tone: "green" });
    } catch (error) {
      showToast({
        title: "Webhook was not saved",
        message: error instanceof Error ? error.message : String(error),
        tone: "red",
      });
    } finally {
      setSavingWebhook(false);
    }
  };

  const toggleWebhook = async () => {
    if (!selectedProduct || savingWebhook) return;
    if (!selectedProduct.webhook_url) {
      setEditingWebhook(true);
      setWebhookEnabled(true);
      return;
    }
    setSavingWebhook(true);
    try {
      await updateProduct(selectedProduct.id, {
        webhook_enabled: !webhookActive,
      });
      showToast({
        title: !webhookActive ? "Webhook enabled" : "Webhook disabled",
        tone: "green",
      });
    } catch (error) {
      showToast({
        title: "Webhook update failed",
        message: error instanceof Error ? error.message : String(error),
        tone: "red",
      });
    } finally {
      setSavingWebhook(false);
    }
  };

  if (!selectedProduct) {
    return (
      <div className="integrations-page">
        <section className="integrations-empty">
          <p>Create or select a product before connecting workflow tools.</p>
        </section>
      </div>
    );
  }

  return (
    <div className="integrations-page">
      <div className="integrations-wrap">
        <header className="integrations-header">
          <p>
            Connect where {selectedProduct.product_name}'s approved contacts and outreach go. Nothing sends or
            exports until you approve a contact.
          </p>
        </header>

        <button className="integration-account-banner" type="button" onClick={() => void connectGmail()}>
          <Info size={16} />
          <span>
            <b>Gmail & account services connect once</b>, on your account - used by all products.
          </span>
          <strong>
            Account connections <ArrowRight size={14} />
          </strong>
        </button>

        <IntegrationGroup title="Sending" />
        <IntegrationRow
          active={gmailConnected}
          logo="G"
          logoTone="gmail"
          title="Gmail"
          status={gmailConnected ? "On" : "Off"}
          statusTone={gmailConnected ? "on" : "off"}
          description={
            gmailConnected ? (
              <>
                <span className="integration-ok">
                  <Check size={12} /> using account Gmail
                </span>{" "}
                - {gmailEmail} - sends this product's approved outreach
              </>
            ) : (
              "Send approved outreach from your connected Gmail account."
            )
          }
          action={
            gmailConnected ? (
              <button
                aria-pressed
                aria-label="Disconnect Gmail"
                className="integration-toggle on"
                disabled={disconnectingGmail}
                type="button"
                onClick={() => void disconnectProductGmail()}
              >
                <span />
              </button>
            ) : (
              <button
                className="integration-button primary"
                disabled={connectingGmail}
                type="button"
                onClick={() => void connectGmail()}
              >
                <PlugZap size={14} />
                {connectingGmail ? "Connecting..." : "Connect"}
              </button>
            )
          }
        />

        <IntegrationRow
          logo="R"
          logoTone="resend"
          title="Resend"
          status="Disabled"
          statusTone="off"
          description="Transactional sending from a verified domain - alternative to Gmail"
          action={
            <button className="integration-button" disabled type="button">
              Enable
            </button>
          }
        />

        <IntegrationGroup title="Workflow outputs" />
        <IntegrationRow
          logo="S"
          logoTone="sheets"
          title="Google Sheets"
          description={
            gmailConnected ? (
              "Google account connected - Sheets export can be wired next."
            ) : (
              <>
                <span className="integration-warn">
                  <AlertTriangle size={12} /> needs Google connected
                </span>{" "}
                - connect in account
              </>
            )
          }
          action={
            <button className="integration-toggle" disabled type="button" aria-label="Google Sheets unavailable">
              <span />
            </button>
          }
        />

        <IntegrationRow
          active={webhookActive}
          logo="{}"
          logoTone="webhook"
          title="Webhook"
          description={
            webhookActive && selectedProduct.webhook_url
              ? selectedProduct.webhook_url
              : "POST approved contacts as JSON - Airtable, Notion, custom, Zapier"
          }
          action={
            <>
              {selectedProduct.webhook_url ? (
                <button className="integration-button" type="button" onClick={() => setEditingWebhook((open) => !open)}>
                  <Link2 size={14} />
                  Edit
                </button>
              ) : (
                <button className="integration-button" type="button" onClick={() => setEditingWebhook(true)}>
                  Configure
                </button>
              )}
              <button
                aria-label={webhookActive ? "Disable webhook" : "Enable webhook"}
                aria-pressed={webhookActive}
                className={webhookActive ? "integration-toggle on" : "integration-toggle"}
                disabled={savingWebhook}
                type="button"
                onClick={() => void toggleWebhook()}
              >
                <span />
              </button>
            </>
          }
        />
        {editingWebhook ? (
          <form
            className="integration-webhook-form"
            onSubmit={(event) => {
              event.preventDefault();
              void saveWebhook();
            }}
          >
            <label className="field">
              <span>Webhook URL</span>
              <input
                autoFocus
                placeholder="https://hooks.example/approved-shortlist"
                value={webhookUrl}
                onChange={(event) => setWebhookUrl(event.target.value)}
              />
              {!webhookUrlValid ? <em>Use a full http or https URL.</em> : null}
            </label>
            <label className="integration-check">
              <input
                checked={webhookEnabled}
                disabled={!webhookUrl.trim()}
                type="checkbox"
                onChange={(event) => setWebhookEnabled(event.target.checked)}
              />
              Enable webhook delivery
            </label>
            <button className="integration-button primary" disabled={!webhookUrlValid || savingWebhook} type="submit">
              <Save size={14} />
              {savingWebhook ? "Saving..." : "Save"}
            </button>
          </form>
        ) : null}

        <IntegrationRow
          logo="H"
          logoTone="hubspot"
          title="HubSpot"
          status="Later"
          statusTone="later"
          description="Create/update CRM contacts with fit verdict and evidence"
          action={
            <button className="integration-button" disabled type="button">
              Soon
            </button>
          }
        />
      </div>
    </div>
  );
}

function IntegrationGroup({ title }: { title: string }) {
  return <div className="integration-group-label">{title}</div>;
}

function IntegrationRow({
  active = false,
  action,
  description,
  logo,
  logoTone,
  status,
  statusTone = "off",
  title,
}: {
  active?: boolean;
  action: ReactNode;
  description: ReactNode;
  logo: string;
  logoTone: "gmail" | "hubspot" | "resend" | "sheets" | "webhook";
  status?: string;
  statusTone?: "later" | "off" | "on";
  title: string;
}) {
  return (
    <section className={active ? "integration-row active" : "integration-row"}>
      <span className={`integration-logo ${logoTone}`}>{logo}</span>
      <div className="integration-main">
        <div className="integration-name">
          <strong>{title}</strong>
          {status ? <span className={`integration-status ${statusTone}`}>{status}</span> : null}
        </div>
        <p>{description}</p>
      </div>
      <div className="integration-actions">{action}</div>
    </section>
  );
}
