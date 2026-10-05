import { ArrowRight, Check, LoaderCircle, MapPin, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type {
  ProfileCreateInput,
  ProfileCustomerKind,
  ProfileExclusion,
  ProfileOptions,
  ProfileSignal,
  ProfileTrade,
} from "../types/domain";

const SIGNALS: Array<{ value: ProfileSignal; label: string }> = [
  { value: "website_unavailable", label: "Missing or unavailable website" },
  { value: "no_quote_flow", label: "No quote or booking flow" },
  { value: "no_contact_form", label: "No contact form" },
  { value: "reviews_under_15", label: "Reviews under 15" },
];

const EXCLUSIONS: Array<{ value: ProfileExclusion; label: string }> = [
  { value: "closed", label: "Closed or inactive" },
  { value: "chains", label: "Chains" },
  { value: "franchises", label: "Franchises" },
  { value: "directories", label: "Directories" },
  { value: "agencies", label: "Marketing agencies" },
];

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
  const [signals, setSignals] = useState<ProfileSignal[]>([]);
  const [exclusions, setExclusions] = useState<ProfileExclusion[]>(EXCLUSIONS.map((item) => item.value));
  const [saving, setSaving] = useState(false);
  const valid = Boolean(selectedProductId && trades.length && city.trim().length >= 2);

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

  if (selectedProfile) {
    const scoring = activeBatch?.state === "scoring";
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
              : activeBatch?.delivery
                ? `${activeBatch.remaining_count} leads remain for review.`
                : "The initial batch is queued for worker processing."}
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
      signals,
      exclude: exclusions,
      limit: batchSize,
      exclude_already_delivered: true,
    };
    setSaving(true);
    try {
      await createProfile(input);
      showToast({ title: "Audience created", message: "The first lead batch is queued.", tone: "green" });
    } catch (error) {
      showToast({ title: "Audience could not be created", message: error instanceof Error ? error.message : String(error), tone: "red" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="audience-setup-screen">
      <header className="audience-page-heading">
        <div>
          <span>{selectedProduct?.product_name || "Product"}</span>
          <h1>New audience</h1>
          <p>Create a separate lead stream under this product.</p>
        </div>
      </header>

      <form
        className="audience-setup-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="audience-name-row">
          <label>
            <span>Name · optional</span>
            <input autoFocus type="text" placeholder={defaultAudienceName(trades, city, businessTypes)} value={name} onChange={(event) => setName(event.target.value)} />
          </label>
        </div>

        <fieldset>
          <legend>Business type <em>*</em></legend>
          <div className="audience-chip-options" aria-label="Business types">
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
            {!profileOptions && !optionsError ? <LoaderCircle className="sl-spin" size={15} /> : null}
            {optionsError ? <span className="audience-options-error">Business types unavailable.</span> : null}
          </div>
        </fieldset>

        <fieldset>
          <legend>Customer kind <em>*</em></legend>
          <div className="audience-radio-options">
            {(["residential", "commercial"] as ProfileCustomerKind[]).map((value) => (
              <label key={value}>
                <input type="radio" name="customer-kind" value={value} checked={customerKind === value} onChange={() => setCustomerKind(value)} />
                <span>{capitalize(value)}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="audience-location-section">
          <label>
            <span>City <em>*</em></span>
            <div className="audience-city-control">
              <MapPin aria-hidden="true" size={15} />
              <input list="audience-city-options" type="text" placeholder="Toronto" value={city} onChange={(event) => setCity(event.target.value)} />
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
          <div className="audience-location-grid">
            {city.trim() ? (
              <label>
                <span>Radius</span>
                <select value={radiusKm} onChange={(event) => setRadiusKm(Number(event.target.value) as 10 | 25 | 50)}>
                  {[10, 25, 50].map((value) => <option key={value} value={value}>{value} km</option>)}
                </select>
              </label>
            ) : <span />}
            <label>
              <span>Batch size</span>
              <select value={batchSize} onChange={(event) => setBatchSize(Number(event.target.value) as 15 | 25 | 40)}>
                {[15, 25, 40].map((value) => <option key={value} value={value}>{value} leads</option>)}
              </select>
            </label>
          </div>
        </div>

        <fieldset>
          <legend>Opportunity signals</legend>
          <div className="audience-option-grid">
            {SIGNALS.map((signal) => (
              <label key={signal.value}>
                <input type="checkbox" checked={signals.includes(signal.value)} onChange={() => setSignals(toggleValue(signals, signal.value))} />
                <span>{signal.label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend>Exclude</legend>
          <div className="audience-option-grid">
            {EXCLUSIONS.map((exclusion) => (
              <label key={exclusion.value}>
                <input type="checkbox" checked={exclusions.includes(exclusion.value)} onChange={() => setExclusions(toggleValue(exclusions, exclusion.value))} />
                <span>{exclusion.label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="audience-form-footer">
          <button className="primary audience-create-button" disabled={!valid || saving} type="submit">
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
  const tradeLabel = trades
    .map((key) => businessTypes.find((trade) => trade.key === key)?.label)
    .filter(Boolean)
    .join(" + ");
  return [tradeLabel, city.trim()].filter(Boolean).join(" · ") || "Painters · Toronto";
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function batchStateLabel(state: string | undefined) {
  if (state === "scoring") return "Scoring batch";
  if (state === "ready") return "Batch ready";
  if (state === "partial") return "Partial batch";
  if (state === "failed") return "Batch failed";
  return "Setting up";
}
