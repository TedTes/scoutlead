import { ArrowLeft, ShieldCheck } from "lucide-react";
import { useMemo, type ReactNode } from "react";
import { ApiClient } from "../api/client";
import { getApiBaseUrl, getStaticApiToken } from "../config/env";
import { AdminDataScreen } from "../screens/AdminDataScreen";
import { ToastProvider } from "../shared-ui";

type AdminAppProps = {
  accountSlot?: ReactNode;
  adminEmail?: string;
  getAuthToken?: () => Promise<string | null>;
};

export function AdminApp({ accountSlot, adminEmail, getAuthToken }: AdminAppProps) {
  const api = useMemo(
    () => new ApiClient({
      baseUrl: getApiBaseUrl(),
      token: getStaticApiToken(),
      getToken: getAuthToken,
    }),
    [getAuthToken],
  );

  return (
    <ToastProvider>
      <div className="admin-shell">
        <header className="admin-shell-header">
          <a className="admin-shell-brand" href="/" aria-label="ScoutLead home">
            <span className="admin-shell-mark">S</span>
            <span>
              <strong>ScoutLead Admin</strong>
              <small><ShieldCheck size={11} /> Data stewardship</small>
            </span>
          </a>
          <div className="admin-shell-account">
            <a href="/app"><ArrowLeft size={14} /> Back to site</a>
            {adminEmail ? <span>{adminEmail}</span> : null}
            {accountSlot}
          </div>
        </header>
        <main className="admin-shell-main">
          <AdminDataScreen api={api} />
        </main>
      </div>
    </ToastProvider>
  );
}
