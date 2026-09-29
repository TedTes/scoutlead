import {
  Building2,
  Check,
  ChevronRight,
  Download,
  MapPinned,
  Pause,
  Play,
  Plus,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppData } from "../state/app-data";
import { useToast } from "../shared-ui";
import type {
  DiscoveryResult,
  LeadOutcomeValue,
  Territory,
  TerritoryDelivery,
  TerritoryMetrics,
  TerritoryResolution,
} from "../types/domain";
import { defaultExportFileName } from "../utils/export-file";

type TerritoryTab = "new" | "working" | "all";

export function TerritoriesScreen() {
  const { selectedProductId, territoryApi } = useAppData();
  const { showToast } = useToast();
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [deliveries, setDeliveries] = useState<TerritoryDelivery[]>([]);
  const [contacts, setContacts] = useState<DiscoveryResult[]>([]);
  const [metrics, setMetrics] = useState<TerritoryMetrics | null>(null);
  const [selectedContactId, setSelectedContactId] = useState("");
  const [tab, setTab] = useState<TerritoryTab>("new");
  const [request, setRequest] = useState("");
  const [resolution, setResolution] = useState<TerritoryResolution | null>(null);
  const [busy, setBusy] = useState(false);

  const selected = territories.find((territory) => territory.id === selectedId);
  const selectedContact = contacts.find((contact) => contact.id === selectedContactId);

  const loadTerritories = useCallback(async () => {
    if (!selectedProductId) {
      setTerritories([]);
      return;
    }
    const rows = (await territoryApi.getTerritories()).filter(
      (territory) => territory.product_id === selectedProductId,
    );
    setTerritories(rows);
    setSelectedId((current) => (rows.some((row) => row.id === current) ? current : rows[0]?.id || ""));
  }, [selectedProductId, territoryApi]);

  const loadTerritory = useCallback(async () => {
    if (!selectedId) {
      setDeliveries([]);
      setContacts([]);
      setMetrics(null);
      return;
    }
    const [nextDeliveries, nextMetrics] = await Promise.all([
      territoryApi.getTerritoryDeliveries(selectedId),
      territoryApi.getTerritoryMetrics(selectedId),
    ]);
    setDeliveries(nextDeliveries);
    setMetrics(nextMetrics);
    const resultGroups = await Promise.all(
      nextDeliveries.map((delivery) =>
        territoryApi.getTerritoryDeliveryContacts(selectedId, delivery.id).catch(() => []),
      ),
    );
    const nextContacts = [...new Map(resultGroups.flat().map((contact) => [contact.id, contact])).values()];
    setContacts(nextContacts);
    setTerritories((current) =>
      current.map((territory) =>
        territory.id === selectedId ? { ...territory, unviewed_delivery_count: 0 } : territory,
      ),
    );
    setSelectedContactId((current) =>
      nextContacts.some((contact) => contact.id === current) ? current : nextContacts[0]?.id || "",
    );
  }, [selectedId, territoryApi]);

  useEffect(() => {
    void loadTerritories().catch((error) =>
      showToast({ title: "Searches unavailable", message: String(error), tone: "red" }),
    );
  }, [loadTerritories, showToast]);

  useEffect(() => {
    void loadTerritory().catch((error) =>
      showToast({ title: "Search unavailable", message: String(error), tone: "red" }),
    );
  }, [loadTerritory, showToast]);

  const visibleContacts = useMemo(() => {
    if (tab === "working") return contacts.filter((contact) => contact.latest_outcome === "contacted");
    if (tab === "new" && deliveries[0]) {
      return contacts.filter((contact) => contact.campaign_id === deliveries[0].campaign_id);
    }
    return contacts;
  }, [contacts, deliveries, tab]);

  const resolve = async () => {
    if (!selectedProductId || request.trim().length < 4) return;
    setBusy(true);
    try {
      setResolution(await territoryApi.resolveTerritory(selectedProductId, request.trim()));
    } catch (error) {
      showToast({ title: "Could not resolve search", message: String(error), tone: "red" });
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    if (!resolution) return;
    setBusy(true);
    try {
      const created = await territoryApi.createTerritory(resolution);
      setRequest("");
      setResolution(null);
      await loadTerritories();
      setSelectedId(created.id);
      showToast({ title: "Search created", message: "The first refresh is ready to run.", tone: "green" });
    } catch (error) {
      showToast({ title: "Could not create search", message: String(error), tone: "red" });
    } finally {
      setBusy(false);
    }
  };

  const refresh = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await territoryApi.refreshTerritory(selected.id);
      await Promise.all([loadTerritories(), loadTerritory()]);
      showToast({ title: "Search refreshed", tone: "green" });
    } catch (error) {
      showToast({ title: "Refresh failed", message: String(error), tone: "red" });
    } finally {
      setBusy(false);
    }
  };

  const toggleStatus = async () => {
    if (!selected) return;
    const status = selected.status === "active" ? "paused" : "active";
    await territoryApi.updateTerritory(selected.id, { status });
    await loadTerritories();
  };

  const exportLatestDelivery = async () => {
    if (!selected || !deliveries[0]) return;
    try {
      const blob = await territoryApi.downloadTerritoryDeliveryCsv(selected.id, deliveries[0].id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${defaultExportFileName(selected.label, "call-sheet")}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      showToast({ title: "Export failed", message: String(error), tone: "red" });
    }
  };

  const recordOutcome = async (outcome: LeadOutcomeValue, channel = "other") => {
    if (!selectedContact) return;
    await territoryApi.recordLeadOutcome(selectedContact.id, outcome, channel);
    await loadTerritory();
    showToast({ title: "Outcome recorded", tone: "green" });
  };

  const generateApproach = async () => {
    if (!selectedContact) return;
    try {
      await territoryApi.generateLeadApproach(selectedContact.id);
      await loadTerritory();
    } catch (error) {
      showToast({ title: "Approach unavailable", message: String(error), tone: "amber" });
    }
  };

  return (
    <section className="territory-workspace">
      <header className="territory-header">
        <div>
          <p className="section-kicker">Searches</p>
          <h1>Recurring searches</h1>
        </div>
        {selected ? (
          <div className="territory-header-actions">
            <button className="secondary-button" disabled={!deliveries.length} type="button" onClick={() => void exportLatestDelivery()}>
              <Download size={14} /> Export call sheet
            </button>
            <button className="secondary-button" type="button" onClick={toggleStatus}>
              {selected.status === "active" ? <Pause size={14} /> : <Play size={14} />}
              {selected.status === "active" ? "Pause" : "Resume"}
            </button>
            <button className="primary-button" disabled={busy || selected.status !== "active"} type="button" onClick={refresh}>
              <RefreshCw size={14} /> Refresh now
            </button>
          </div>
        ) : null}
      </header>

      <div className="territory-layout">
        <aside className="territory-list-panel">
          <form
            className="territory-create"
            onSubmit={(event) => {
              event.preventDefault();
              void resolve();
            }}
          >
            <label htmlFor="territory-request">New search</label>
            <div>
              <input
                id="territory-request"
                placeholder="HVAC contractors in Toronto"
                value={request}
                onChange={(event) => {
                  setRequest(event.target.value);
                  setResolution(null);
                }}
              />
              <button aria-label="Configure search" disabled={busy || request.trim().length < 4} type="submit">
                <Plus size={15} />
              </button>
            </div>
          </form>
          {resolution ? (
            <div className="territory-confirm">
              <span><Building2 size={13} /> {resolution.niche_label}</span>
              <span><MapPinned size={13} /> {resolution.market_label}</span>
              <button type="button" onClick={() => void create()}><Check size={14} /> Confirm</button>
            </div>
          ) : null}
          <div className="territory-list">
            {territories.map((territory) => (
              <button
                className={territory.id === selectedId ? "territory-row active" : "territory-row"}
                key={territory.id}
                type="button"
                onClick={() => setSelectedId(territory.id)}
              >
                <span>
                  <strong>
                    {territory.label}
                    {territory.unviewed_delivery_count ? <b className="territory-new-badge">New</b> : null}
                  </strong>
                  <small>
                    {territory.status} · next {formatTerritoryDate(territory.next_run_at)}
                  </small>
                  <small>
                    {territory.last_delivery_count} last delivery · {Math.round(territory.positive_outcome_rate * 100)}% positive
                  </small>
                </span>
                <ChevronRight size={15} />
              </button>
            ))}
            {!territories.length ? <p className="territory-empty">No recurring searches for this sales profile.</p> : null}
          </div>
        </aside>

        <div className="territory-results">
          {selected ? (
            <>
              <div className="territory-summary">
                <div><span>Delivered</span><strong>{metrics?.totals.delivered ?? 0}</strong></div>
                <div><span>Contacted</span><strong>{metrics?.totals.contacted ?? 0}</strong></div>
                <div><span>Meetings</span><strong>{metrics?.totals.meetings ?? 0}</strong></div>
                <div><span>Outcome coverage</span><strong>{Math.round((metrics?.totals.outcome_coverage ?? 0) * 100)}%</strong></div>
              </div>
              <div className="territory-tabs" role="tablist">
                {(["new", "working", "all"] as TerritoryTab[]).map((value) => (
                  <button className={tab === value ? "active" : ""} key={value} type="button" onClick={() => setTab(value)}>
                    {value === "new" ? "New this week" : value === "working" ? "Working" : "All"}
                  </button>
                ))}
              </div>
              <div className="territory-contact-layout">
                <div className="territory-contacts">
                  {visibleContacts.map((contact) => (
                    <button
                      className={contact.id === selectedContactId ? "territory-contact active" : "territory-contact"}
                      key={contact.id}
                      type="button"
                      onClick={() => setSelectedContactId(contact.id)}
                    >
                      <span><strong>{contact.company_name}</strong><small>{contact.contact_email || contact.geography || "No contact detail"}</small></span>
                      <em>{contact.latest_outcome?.replace(/_/g, " ") || "new"}</em>
                    </button>
                  ))}
                  {!visibleContacts.length ? <p className="territory-empty">No contacts in this view.</p> : null}
                </div>
                {selectedContact ? (
                  <ContactOutcomePanel
                    contact={selectedContact}
                    onGenerateApproach={generateApproach}
                    onOutcome={recordOutcome}
                  />
                ) : null}
              </div>
            </>
          ) : (
            <div className="territory-blank"><MapPinned size={22} /><strong>Create a search to start weekly prospecting.</strong></div>
          )}
        </div>
      </div>
    </section>
  );
}

function formatTerritoryDate(value?: string | null) {
  if (!value) return "not scheduled";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(value));
}

function ContactOutcomePanel({
  contact,
  onGenerateApproach,
  onOutcome,
}: {
  contact: DiscoveryResult;
  onGenerateApproach: () => Promise<void>;
  onOutcome: (outcome: LeadOutcomeValue, channel?: string) => Promise<void>;
}) {
  return (
    <aside className="territory-contact-detail">
      <div className="territory-contact-heading">
        <div><p>Selected contact</p><h2>{contact.company_name}</h2></div>
        <span>{contact.qualification?.fit_status?.replace(/_/g, " ") || "unscored"}</span>
      </div>
      {contact.outcome_adjustment ? (
        <p className="territory-rank-reason">
          Why ranked here: outcome evidence adjusted this contact by {contact.outcome_adjustment > 0 ? "+" : ""}
          {contact.outcome_adjustment.toFixed(1)}
          {contact.qualification?.signal_tags?.length
            ? ` from ${contact.qualification.signal_tags.slice(0, 3).join(", ")}`
            : ""}.
        </p>
      ) : null}
      {contact.approach ? (
        <section className="territory-approach">
          <span>Best channel · {contact.approach.best_channel.replace(/_/g, " ")}</span>
          <p>{contact.approach.opener}</p>
          {contact.approach.talk_track?.length ? (
            <ul>{contact.approach.talk_track.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : null}
        </section>
      ) : (
        <button className="secondary-button" type="button" onClick={() => void onGenerateApproach()}>
          Prepare approach
        </button>
      )}
      <OutcomeGroup title="Contacted by" actions={[
        ["Email", "contacted", "email"], ["Phone", "contacted", "phone"], ["Visit", "contacted", "visit"],
      ]} onOutcome={onOutcome} />
      <OutcomeGroup title="Result" actions={[
        ["Positive reply", "replied_positive"], ["Negative reply", "replied_negative"],
        ["Meeting", "meeting_booked"], ["Won", "won"],
      ]} onOutcome={onOutcome} />
      <OutcomeGroup title="Data problem" actions={[
        ["Not a fit", "not_a_fit"], ["Wrong contact", "wrong_contact"], ["Closed", "business_closed"],
      ]} onOutcome={onOutcome} />
    </aside>
  );
}

function OutcomeGroup({
  title,
  actions,
  onOutcome,
}: {
  title: string;
  actions: Array<[string, LeadOutcomeValue, string?]>;
  onOutcome: (outcome: LeadOutcomeValue, channel?: string) => Promise<void>;
}) {
  return (
    <section className="outcome-group">
      <h3>{title}</h3>
      <div>{actions.map(([label, outcome, channel]) => (
        <button key={`${outcome}-${channel || ""}`} type="button" onClick={() => void onOutcome(outcome, channel)}>{label}</button>
      ))}</div>
    </section>
  );
}
