import { ArrowRight, Check, LoaderCircle, MapPin, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type {
  ProfileCreateInput,
  ProfileCustomerKind,
  ProfileExclusion,
  ProfileOptions,
  ProfileTrade,
} from "../types/domain";

const FALLBACK_SERVICES: ProfileOptions["services"] = [
  {
    key: "website_modernization",
    label: "Website presence and modernization",
    description: "Missing, insecure, or low-quality website.",
    status: "active", enabled: true, signals: [],
  },
  {
    key: "lead_capture",
    label: "Lead capture and conversion",
    description: "Missing contact paths, calls to action, or business details.",
    status: "active", enabled: true, signals: [],
  },
  {
    key: "booking_payments",
    label: "Quotes, booking, and payments",
    description: "Missing quote, scheduling, payment, or financing flows.",
    status: "active", enabled: true, signals: [],
  },
  {
    key: "performance_accessibility",
    label: "Mobile performance and accessibility",
    description: "Slow, unstable, inaccessible, or poorly adapted mobile experience.",
    status: "active", enabled: true, signals: [],
  },
  {
    key: "local_visibility",
    label: "Local SEO and service-area visibility",
    description: "Weak search readiness or missing local service content.",
    status: "active", enabled: true, signals: [],
  },
  {
    key: "reputation_trust",
    label: "Reputation and trust",
    description: "Weak reviews or missing customer and compliance signals.",
    status: "active", enabled: true, signals: [],
  },
  {
    key: "multilingual_localization",
    label: "Multilingual website localization",
    description: "Missing language declarations, alternate pages, or local-language support.",
    status: "draft", enabled: false, signals: [{ key: "market_language_supported", label: "Market language supported", weight: 1 }],
  },
  {
    key: "crm_follow_up_automation",
    label: "CRM and follow-up automation",
    description: "Missed responses, inconsistent follow-up, or manual lead handling.",
    status: "draft", enabled: false, signals: [],
  },
  {
    key: "social_media_management",
    label: "Social media management",
    description: "Inactive profiles, inconsistent publishing, or weak social engagement.",
    status: "draft", enabled: false, signals: [],
  },
  {
    key: "branding_creative",
    label: "Branding and creative services",
    description: "Outdated or inconsistent branding across public customer touchpoints.",
    status: "draft", enabled: false, signals: [],
  },
  {
    key: "recruiting_employer_branding",
    label: "Recruiting and employer branding",
    description: "Active hiring with weak recruiting pages or employer positioning.",
    status: "draft", enabled: false, signals: [],
  },
  {
    key: "maintenance_plan_consulting",
    label: "Maintenance-plan consulting",
    description: "No visible recurring service or customer-retention offering.",
    status: "draft", enabled: false, signals: [],
  },
];

const SYSTEM_EXCLUSIONS: ProfileExclusion[] = ["closed", "directories"];

const CITY_SUGGESTIONS = [
  "Toronto",
  "North York",
  "Scarborough",
  "Etobicoke",
  "Mississauga",
  "Brampton",
  "Vaughan",
  "Markham",
];

export function AudienceProfileScreen() {
  const { createProfile, profileBatch, selectedProduct, selectedProductId, selectedProfile, territoryApi } = useAppData();
  const { showToast } = useToast();
  const [profileOptions, setProfileOptions] = useState<ProfileOptions | null>(null);
  const [optionsError, setOptionsError] = useState(false);
  const [name, setName] = useState("");
  const [trades, setTrades] = useState<ProfileTrade[]>([]);
  const [customerKind, setCustomerKind] = useState<ProfileCustomerKind>("residential");
  const [city, setCity] = useState("");
  const [radiusKm, setRadiusKm] = useState<10 | 25 | 50>(25);
  const [batchSize, setBatchSize] = useState<15 | 25 | 40>(25);
  const [services, setServices] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const audienceDefined = Boolean(trades.length && city.trim().length >= 2);
  const valid = Boolean(selectedProductId && audienceDefined);

  const activeBatch = useMemo(
    () => profileBatch?.profile.id === selectedProfile?.id ? profileBatch : null,
    [profileBatch, selectedProfile?.id],
  );

  useEffect(() => {
    let active = true;
    setOptionsError(false);
    void territoryApi.getProfileOptions().then(
      (options) => {
        if (active) setProfileOptions(options);
      },
      () => {
        if (active) setOptionsError(true);
      },
    );
    return () => {
      active = false;
    };
  }, [territoryApi]);

  const businessTypes = profileOptions?.business_types || [];
  const serviceOptions = useMemo(() => {
    const merged = new Map(FALLBACK_SERVICES.map((service) => [service.key, service]));
    for (const service of profileOptions?.services || []) merged.set(service.key, service);
    return [...merged.values()];
  }, [profileOptions?.services]);

  if (selectedProfile) {
    const scoring = activeBatch?.state === "scoring" || activeBatch?.state === "retrying";
    const tradeLabel = selectedProfile.trade_keys
      .map((key) => businessTypes.find((trade) => trade.key === key)?.label || key)
      .join(", ");
    return (
      <section className="audience-status-screen">
        <header className="audience-page-heading">
          <div>
            <span>Audience</span>
            <h1>{selectedProfile.label}</h1>
            <p>
              {tradeLabel || "Local businesses"} · {capitalize(selectedProfile.customer_kind)} · {selectedProfile.city} · {selectedProfile.radius_km} km
            </p>
          </div>
        </header>
        <div className="audience-status-panel">
          <span className={`audience-state is-${activeBatch?.state || "setup"}`}>
            {scoring ? <LoaderCircle className="sl-spin" size={15} /> : <Check size={15} />}
            {batchStateLabel(activeBatch?.state)}
          </span>
          <strong>{activeBatch?.result_count || 0} leads in the current batch</strong>
          <p>
            {scoring
              ? "ScoutLead is scoring indexed businesses for this audience. You can leave this page."
              : activeBatch && ["ready", "partial"].includes(activeBatch.state)
                ? `${activeBatch.remaining_count} leads remain for review.`
                : activeBatch?.state === "setup"
                  ? "No lead batch has been generated for this audience yet."
                  : activeBatch?.state === "failed"
                    ? "The latest batch could not be completed."
                    : "No indexed businesses matched this audience."}
          </p>
        </div>
      </section>
    );
  }

  const submit = async () => {
    if (!valid || saving) return;
    const input: ProfileCreateInput = {
      product_id: selectedProductId,
      ...(name.trim() ? { name: name.trim() } : {}),
      trades,
      customer_kind: customerKind,
      market: { city: city.trim(), radius_km: radiusKm },
      services,
      signals: [],
      exclude: SYSTEM_EXCLUSIONS,
      limit: batchSize,
      refill_policy: "when_depleted",
      exclude_already_delivered: true,
    };
    setSaving(true);
    try {
      await createProfile(input);
      showToast({ title: "Audience ready", message: "A refresh is queued and existing leads remain available.", tone: "green" });
    } catch (error) {
      showToast({ title: "Audience could not be created", message: error instanceof Error ? error.message : String(error), tone: "red" });
    } finally {
      setSaving(false);
    }
  };

  const formHint = getFormHint(trades, city, services);

  return (
    <section className="audience-setup-screen">
      <header className="audience-page-heading">
        <div>
          <span>{selectedProduct?.product_name || "Product"}</span>
          <h1>
            Define your <em>next</em> audience
          </h1>
          <p className="audience-brief">
            {audienceDefined ? (
              <>
                <span className="audience-brief-value">{capitalize(customerKind)}</span>{" "}
                <span className="audience-brief-value">
                  {joinLabels(trades.map((key) => businessTypes.find((trade) => trade.key === key)?.label || key))}
                </span>
                {" in "}
                <span className="audience-brief-value">{city.trim()}</span>
                {`, within ${radiusKm} km. First batch: ${batchSize} leads.`}
              </>
            ) : (
              <>Set the business type and market for this product.</>
            )}
          </p>
        </div>
      </header>

      <form
        className="audience-setup-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <section className="audience-form-row" aria-labelledby="audience-name-title">
          <div className="audience-row-copy">
            <h2 id="audience-name-title">Name</h2>
            <p>Optional. Leave blank to use the business type and city.</p>
          </div>
          <div className="audience-row-control">
            <input
              aria-label="Audience name"
              autoFocus
              className="audience-input"
              placeholder={defaultAudienceName(trades, city, businessTypes)}
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
        </section>

        <section className="audience-form-row" aria-labelledby="audience-trade-title">
          <div className="audience-row-copy">
            <h2 id="audience-trade-title">Business type <em>*</em></h2>
            <p>Choose one or more.</p>
          </div>
          <div className="audience-row-control">
            <div className="audience-chip-options" role="group" aria-labelledby="audience-trade-title">
              {businessTypes.map((trade) => {
                const selected = trades.includes(trade.key);
                return (
                  <button
                    aria-pressed={selected}
                    className={selected ? "is-selected" : ""}
                    key={trade.key}
                    type="button"
                    onClick={() => setTrades(toggleValue(trades, trade.key))}
                  >
                    {selected ? <Check size={13} /> : null}
                    {trade.label}
                  </button>
                );
              })}
            </div>
            {!profileOptions && !optionsError ? (
              <p className="audience-row-status">
                <LoaderCircle className="sl-spin" size={14} />
                Loading business types
              </p>
            ) : null}
            {optionsError ? <p className="audience-row-error">Business types unavailable.</p> : null}
          </div>
        </section>

        <section className="audience-form-row" aria-labelledby="audience-kind-title">
          <div className="audience-row-copy">
            <h2 id="audience-kind-title">Customer kind <em>*</em></h2>
            <p>Who these businesses serve.</p>
          </div>
          <div className="audience-row-control">
            <div className="audience-segmented" role="radiogroup" aria-labelledby="audience-kind-title">
              {(["residential", "commercial"] as ProfileCustomerKind[]).map((value) => (
                <label key={value}>
                  <input type="radio" name="customer-kind" value={value} checked={customerKind === value} onChange={() => setCustomerKind(value)} />
                  <span>{capitalize(value)}</span>
                </label>
              ))}
            </div>
          </div>
        </section>

        <section className="audience-form-row" aria-labelledby="audience-market-title">
          <div className="audience-row-copy">
            <h2 id="audience-market-title">Market <em>*</em></h2>
            <p>Where these businesses are located.</p>
          </div>
          <div className="audience-market-fields">
            <label className="audience-field">
              <span>City</span>
              <div className="audience-city-control">
                <MapPin aria-hidden="true" size={15} />
                <input
                  className="audience-city-input"
                  list="audience-city-options"
                  minLength={2}
                  placeholder="Enter a city"
                  required
                  type="text"
                  value={city}
                  onChange={(event) => setCity(event.target.value)}
                />
                {city ? (
                  <button aria-label="Clear city" title="Clear city" type="button" onClick={() => setCity("")}>
                    <X size={14} />
                  </button>
                ) : null}
              </div>
              <datalist id="audience-city-options">
                {CITY_SUGGESTIONS.map((value) => <option key={value} value={value} />)}
              </datalist>
            </label>
            <label className="audience-field">
              <span>Radius</span>
              <select
                className="audience-input"
                disabled={!city.trim()}
                value={radiusKm}
                onChange={(event) => setRadiusKm(Number(event.target.value) as 10 | 25 | 50)}
              >
                {[10, 25, 50].map((value) => <option key={value} value={value}>{value} km</option>)}
              </select>
            </label>
          </div>
        </section>

        <section className="audience-form-row" aria-labelledby="audience-delivery-title">
          <div className="audience-row-copy">
            <h2 id="audience-delivery-title">Delivery</h2>
            <p>How many leads to include in the first batch.</p>
          </div>
          <div className="audience-delivery-fields">
            <label className="audience-field">
              <span>Batch size</span>
              <select
                className="audience-input"
                value={batchSize}
                onChange={(event) => setBatchSize(Number(event.target.value) as 15 | 25 | 40)}
              >
                {[15, 25, 40].map((value) => <option key={value} value={value}>{value} leads</option>)}
              </select>
            </label>
          </div>
        </section>

        <section className="audience-form-row" aria-labelledby="audience-signals-title">
          <div className="audience-row-copy">
            <h2 id="audience-signals-title">Services you provide</h2>
            <p>Optional. Select services to prioritize businesses showing evidence they need them.</p>
          </div>
          <div className="audience-row-control">
            <div className="audience-focus-list" role="group" aria-labelledby="audience-signals-title">
              {serviceOptions.map((service) => {
                const selected = services.includes(service.key);
                const enabled = service.enabled ?? (service.status ? service.status === "active" : true);
                const availability = service.signals.length ? "Preparing data" : "Coming soon";
                return (
                  <label className={`${selected ? "is-selected" : ""}${enabled ? "" : " is-disabled"}`} key={service.key}>
                    <input
                      type="checkbox"
                      checked={selected}
                      disabled={!enabled}
                      onChange={() => setServices(toggleValue(services, service.key))}
                    />
                    <span>
                      <strong>{service.label}{!enabled ? <em>{availability}</em> : null}</strong>
                      <small>{service.description}</small>
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
        </section>

        <div className="audience-form-footer">
          <p className="audience-form-hint" aria-live="polite">{formHint}</p>
          <button className="runbtn audience-create-button" disabled={!valid || saving} type="submit">
            {saving ? <LoaderCircle className="sl-spin" size={15} /> : null}
            <span>Create audience</span>
            {!saving ? <ArrowRight size={15} /> : null}
          </button>
        </div>
      </form>
    </section>
  );
}

function toggleValue<T extends string>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function defaultAudienceName(
  trades: ProfileTrade[],
  city: string,
  businessTypes: ProfileOptions["business_types"],
) {
  const tradeLabel = joinLabels(trades.map((key) => businessTypes.find((trade) => trade.key === key)?.label || key));
  return [tradeLabel, city.trim()].filter(Boolean).join(" · ") || "Local businesses";
}

function joinLabels(labels: string[]) {
  if (labels.length <= 2) return labels.join(" and ");
  return `${labels.slice(0, -1).join(", ")}, and ${labels[labels.length - 1]}`;
}

function getFormHint(trades: ProfileTrade[], city: string, services: string[]) {
  const needsBusinessType = trades.length === 0;
  const needsCity = city.trim().length < 2;
  if (needsBusinessType && needsCity) return "Choose a business type and enter a city to continue.";
  if (needsBusinessType) return "Choose a business type to continue.";
  if (needsCity) return "Enter a city to continue.";
  if (!services.length) return "Ready to create a broad audience.";
  return "Ready to create this audience.";
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function batchStateLabel(state: string | undefined) {
  if (state === "scoring") return "Scoring batch";
  if (state === "retrying") return "Retrying batch";
  if (state === "ready") return "Batch ready";
  if (state === "empty") return "No matches";
  if (state === "partial") return "Partial batch";
  if (state === "failed") return "Batch failed";
  return "Setting up";
}
