import { Activity, BriefcaseBusiness, Database, ListChecks, MessageSquareText, ShieldCheck } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { ApiClient } from "../api/client";
import { getApiBaseUrl, getStaticApiToken } from "../config/env";
import { AdminDataScreen } from "../screens/AdminDataScreen";
import { AdminDataJobsScreen } from "../screens/AdminDataJobsScreen";
import { AdminSignalsScreen } from "../screens/AdminSignalsScreen";
import { AdminServicesScreen } from "../screens/AdminServicesScreen";
import { AdminOutreachPlaybooksScreen } from "../screens/AdminOutreachPlaybooksScreen";
import { ToastProvider } from "../shared-ui";

type AdminAppProps = {
  accountSlot?: ReactNode;
  adminEmail?: string;
  getAuthToken?: () => Promise<string | null>;
};

export function AdminApp({ accountSlot, adminEmail, getAuthToken }: AdminAppProps) {
  const [view, setView] = useState<"businesses" | "jobs" | "signals" | "services" | "outreach">("businesses");
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
        </header>
        <div className="admin-shell-layout">
          <nav className="admin-section-nav" aria-label="Admin sections">
            <button className={view === "businesses" ? "active" : ""} title="Leads" type="button" onClick={() => setView("businesses")}><ListChecks size={15} /><span>Leads</span></button>
            <button className={view === "jobs" ? "active" : ""} title="Sources" type="button" onClick={() => setView("jobs")}><Database size={15} /><span>Sources</span></button>
            <button className={view === "signals" ? "active" : ""} title="Signals" type="button" onClick={() => setView("signals")}><Activity size={15} /><span>Signals</span></button>
            <button className={view === "services" ? "active" : ""} title="Services" type="button" onClick={() => setView("services")}><BriefcaseBusiness size={15} /><span>Services</span></button>
            <button className={view === "outreach" ? "active" : ""} title="Outreach" type="button" onClick={() => setView("outreach")}><MessageSquareText size={15} /><span>Outreach</span></button>
            <div className="admin-sidebar-account">
              {accountSlot}
              {adminEmail ? <span title={adminEmail}>{adminEmail}</span> : null}
            </div>
          </nav>
          <main className="admin-shell-main">
            {view === "businesses" ? <AdminDataScreen api={api} /> : view === "jobs" ? <AdminDataJobsScreen api={api} /> : view === "signals" ? <AdminSignalsScreen api={api} /> : view === "services" ? <AdminServicesScreen api={api} /> : <AdminOutreachPlaybooksScreen api={api} />}
          </main>
        </div>
      </div>
    </ToastProvider>
  );
}
