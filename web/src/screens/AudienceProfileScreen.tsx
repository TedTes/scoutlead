import { ArrowRight, Check, ChevronDown, Copy, LoaderCircle, MapPin, Pencil, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { PlaceOption, ProfileCreateInput, ProfileExclusion, ProfileOptions, Territory } from "../types/domain";

const SYSTEM_EXCLUSIONS: ProfileExclusion[] = ["closed", "directories"];
type FormMode = "create" | "edit" | "clone";

export function AudienceProfileScreen({ defaultFolderId = "" }: { defaultFolderId?: string }) {
  const { audienceFolders, createProfile, updateProfile, profileBatch, selectedProduct, selectedProductId, selectedProfile, territoryApi } = useAppData();
  const { showToast } = useToast();
  const [profileOptions, setProfileOptions] = useState<ProfileOptions | null>(null);
  const [optionsError, setOptionsError] = useState(false);
  const [mode, setMode] = useState<FormMode>("create");
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [nicheId, setNicheId] = useState("");
  const [tradeQuery, setTradeQuery] = useState("");
  const [placeQuery, setPlaceQuery] = useState("");
  const [selectedPlace, setSelectedPlace] = useState<PlaceOption | null>(null);
  const [placeOptions, setPlaceOptions] = useState<PlaceOption[]>([]);
  const [placeBusy, setPlaceBusy] = useState(false);
  const [placeOpen, setPlaceOpen] = useState(false);
  const [radiusKm, setRadiusKm] = useState(25);
  const [batchSize, setBatchSize] = useState(25);
  const [refillPolicy, setRefillPolicy] = useState<Territory["refill_policy"]>("when_depleted");
  const [folderId, setFolderId] = useState(defaultFolderId);
  const [services, setServices] = useState<string[]>([]);
  const [hoveredService, setHoveredService] = useState<string | null>(null);
  const [upcomingOpen, setUpcomingOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const submittingRef = useRef(false);

  useEffect(() => {
    let active = true;
    setOptionsError(false);
    void territoryApi.getProfileOptions().then(
      (options) => { if (active) setProfileOptions(options); },
      () => { if (active) setOptionsError(true); },
    );
    return () => { active = false; };
  }, [territoryApi]);

  useEffect(() => {
    if (mode === "create" && !editing) setFolderId(defaultFolderId);
  }, [defaultFolderId, editing, mode]);

  useEffect(() => {
    if (!placeOpen || selectedPlace?.label === placeQuery || placeQuery.trim().length < 2) {
      if (placeQuery.trim().length < 2) setPlaceOptions([]);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      setPlaceBusy(true);
      void territoryApi.searchPlaces(placeQuery.trim()).then(
        (options) => { if (active) setPlaceOptions(options); },
        () => { if (active) setPlaceOptions([]); },
      ).finally(() => { if (active) setPlaceBusy(false); });
    }, 300);
    return () => { active = false; window.clearTimeout(timer); };
  }, [placeOpen, placeQuery, selectedPlace?.label, territoryApi]);

  const businessTypes = profileOptions?.business_types || [];
  const selectedNiche = businessTypes.find((option) => option.id === nicheId);
  const showTradeSearch = businessTypes.length > 12;
  const visibleBusinessTypes = useMemo(() => {
    const query = showTradeSearch ? tradeQuery.trim().toLowerCase() : "";
    return query
      ? businessTypes.filter((option) => `${option.label} ${option.category || ""}`.toLowerCase().includes(query))
      : businessTypes;
  }, [businessTypes, showTradeSearch, tradeQuery]);
  const serviceOptions = profileOptions?.services || [];
  const enabledServices = serviceOptions.filter((service) => service.enabled);
  const upcomingServices = serviceOptions.filter((service) => !service.enabled);
  const enabledServiceKeys = new Set(enabledServices.map((service) => service.key));
  const activeService = serviceOptions.find((service) => service.key === hoveredService);
  const valid = Boolean(selectedProductId && nicheId && selectedPlace && services.length && services.every((service) => enabledServiceKeys.has(service)));
  const activeBatch = useMemo(() => profileBatch?.audience.id === selectedProfile?.id ? profileBatch : null, [profileBatch, selectedProfile?.id]);

  const beginEdit = (nextMode: "edit" | "clone") => {
    if (!selectedProfile) return;
    setMode(nextMode);
    setEditing(true);
    setName(nextMode === "clone" ? `${selectedProfile.label} copy` : selectedProfile.label);
    setNicheId(selectedProfile.niche_id);
    const place = profilePlace(selectedProfile);
    setSelectedPlace(place);
    setPlaceQuery(place?.label || selectedProfile.place_label || selectedProfile.city);
    setRadiusKm(selectedProfile.radius_km);
    setBatchSize(selectedProfile.batch_size);
    setRefillPolicy(selectedProfile.refill_policy);
    setFolderId(selectedProfile.folder_id || "");
    setServices(selectedProfile.service_keys);
  };

  if (selectedProfile && !editing) {
    const scoring = activeBatch?.state === "scoring" || activeBatch?.state === "retrying";
    return <section className="audience-status-screen">
      <header className="audience-page-heading audience-status-heading"><div><span>Audience</span><h1>{selectedProfile.label}</h1><p>{selectedProfile.niche_label || "Local businesses"} · {selectedProfile.place_label || selectedProfile.city} · {selectedProfile.radius_km} km</p></div><div className="audience-status-actions"><button className="secondary" type="button" onClick={() => beginEdit("clone")}><Copy size={14} /> Clone</button><button className="secondary" type="button" onClick={() => beginEdit("edit")}><Pencil size={14} /> Edit</button></div></header>
      <div className="audience-status-panel"><span className={`audience-state is-${activeBatch?.state || "setup"}`}>{scoring ? <LoaderCircle className="sl-spin" size={15} /> : <Check size={15} />}{batchStateLabel(activeBatch?.state)}</span><strong>{activeBatch?.result_count || 0} leads in the current batch</strong><p>{batchStateCopy(activeBatch)}</p></div>
    </section>;
  }

  const submit = async () => {
    if (!valid || !selectedPlace || submittingRef.current) return;
    submittingRef.current = true;
    setSaving(true);
    const customerKind = mode === "create" ? "both" : selectedProfile?.customer_kind || "both";
    const market = { place_label: selectedPlace.label, place_provider: selectedPlace.provider, place_external_id: selectedPlace.external_id, country_code: selectedPlace.country_code, latitude: selectedPlace.latitude, longitude: selectedPlace.longitude, radius_km: radiusKm };
    try {
      if (mode === "edit" && selectedProfile) {
        await updateProfile(selectedProfile.id, { label: name.trim() || autoName(selectedNiche?.label, selectedPlace, radiusKm, services, serviceOptions), folder_id: folderId || null, niche_id: nicheId, customer_kind: customerKind, ...market, service_keys: services, batch_size: batchSize, refill_policy: refillPolicy, exclusion_keys: SYSTEM_EXCLUSIONS });
        setEditing(false);
        showToast({ title: "Audience updated", message: "New criteria will apply to the next batch.", tone: "green" });
      } else {
        const input: ProfileCreateInput = { product_id: selectedProductId, folder_id: folderId || null, name: name.trim() || autoName(selectedNiche?.label, selectedPlace, radiusKm, services, serviceOptions), niche_id: nicheId, customer_kind: customerKind, market, services, signals: [], exclude: SYSTEM_EXCLUSIONS, limit: batchSize, refill_policy: refillPolicy, exclude_already_delivered: true, ...(mode === "clone" && selectedProfile ? { clone_from_id: selectedProfile.id } : {}) };
        await createProfile(input);
        setEditing(false);
        setMode("create");
        showToast({ title: mode === "clone" ? "Audience cloned" : "Audience ready", message: "The initial batch is queued.", tone: "green" });
      }
    } catch (error) {
      showToast({ title: "Audience could not be saved", message: error instanceof Error ? error.message : String(error), tone: "red" });
    } finally {
      submittingRef.current = false;
      setSaving(false);
    }
  };

  const formHint = getFormHint(nicheId, selectedPlace, services);
  const generatedName = autoName(selectedNiche?.label, selectedPlace, radiusKm, services, serviceOptions);
  const opportunityHelp = activeService?.description
    || (services.length ? `${services.length} selected — leads must show evidence of at least one.` : "Choose the business gap ScoutLead should verify with evidence.");

  return <section className="audience-setup-screen audience-compact-screen">
    <header className="audience-page-heading audience-compact-heading"><div><span>{selectedProduct?.product_name || "Product"}</span><h1>{mode === "edit" ? "Edit audience" : mode === "clone" ? "Clone audience" : <>Define your <em>next</em> audience</>}</h1><p>Who to find, where, and the opportunity to verify.</p></div></header>
    <form className="audience-compact-form" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <div className="audience-compact-card">
        <section className="audience-compact-section" aria-labelledby="audience-trade-title">
          <header className="audience-section-heading"><span>01</span><h2 id="audience-trade-title">Who you’re targeting</h2></header>
          <div className="audience-compact-field">
            {showTradeSearch ? <label htmlFor="audience-trade-search">Trade</label> : <span className="audience-compact-label">Trade</span>}
            {showTradeSearch ? <div className="audience-trade-search"><Search aria-hidden="true" size={14} /><input autoComplete="off" id="audience-trade-search" placeholder="Search trades…" type="search" value={tradeQuery} onChange={(event) => setTradeQuery(event.target.value)} /></div> : null}
            <div className="audience-trade-chips" role="listbox" aria-label="Trade">
              {visibleBusinessTypes.map((businessType) => <button aria-selected={nicheId === businessType.id} className={nicheId === businessType.id ? "is-selected" : ""} key={businessType.id} role="option" type="button" onClick={() => setNicheId(businessType.id)}>{nicheId === businessType.id ? <Check size={13} /> : null}{shortTradeLabel(businessType.label)}</button>)}
            </div>
            {!profileOptions && !optionsError ? <p className="audience-row-status"><LoaderCircle className="sl-spin" size={14} />Loading trades</p> : null}
            {profileOptions && !visibleBusinessTypes.length ? <p className="audience-empty-options">No trades match “{tradeQuery}”.</p> : null}
            {optionsError ? <p className="audience-row-error">Trades are unavailable.</p> : null}
          </div>
        </section>

        <section className="audience-compact-section" aria-labelledby="audience-market-title">
          <header className="audience-section-heading"><span>02</span><h2 id="audience-market-title">Where to search</h2></header>
          <div className="audience-compact-field audience-location-field">
            <label htmlFor="audience-place-search">Location</label>
            <div className={`audience-place-picker${selectedPlace ? " is-confirmed" : ""}`}>
              {selectedPlace ? <Check aria-hidden="true" size={15} /> : <MapPin aria-hidden="true" size={15} />}
              <input autoComplete="off" id="audience-place-search" placeholder="Search for a city" value={placeQuery} onFocus={() => setPlaceOpen(true)} onChange={(event) => { setPlaceQuery(event.target.value); setSelectedPlace(null); setPlaceOpen(true); }} />
              {placeBusy ? <LoaderCircle className="sl-spin" size={14} /> : null}
              {placeQuery ? <button aria-label="Clear place" type="button" onClick={() => { setPlaceQuery(""); setSelectedPlace(null); setPlaceOptions([]); }}><X size={14} /></button> : null}
              {placeOpen && placeOptions.length ? <div className="audience-place-options" role="listbox">{placeOptions.map((place) => <button aria-selected="false" key={`${place.provider}:${place.external_id || place.label}`} role="option" type="button" onClick={() => { setSelectedPlace(place); setPlaceQuery(place.label); setPlaceOpen(false); setPlaceOptions([]); }}><MapPin size={14} /><span>{place.label}</span></button>)}</div> : null}
            </div>
            {selectedPlace ? <p className="audience-place-resolved"><Check size={12} />Resolved to {selectedPlace.label} · {placeProviderLabel(selectedPlace.provider)}</p> : <p className="audience-field-help">Select a result to confirm the search center.</p>}
            <div className="audience-radius-options audience-compact-radius" role="radiogroup" aria-label="Coverage radius">
              {(profileOptions?.radius_presets || [10, 25, 50]).map((value) => <button aria-pressed={radiusKm === value} className={radiusKm === value ? "is-selected" : ""} disabled={!selectedPlace} key={value} type="button" onClick={() => setRadiusKm(value)}>{value} km</button>)}
            </div>
          </div>
        </section>

        <section className="audience-compact-section" aria-labelledby="audience-signals-title">
          <header className="audience-section-heading"><span>03</span><h2 id="audience-signals-title">Opportunity to verify</h2><small>Choose one or more</small></header>
          <div className="audience-opportunity-chips" role="listbox" aria-describedby="audience-opportunity-help" aria-label="Opportunities">
            {enabledServices.map((service) => { const selected = services.includes(service.key); return <button aria-selected={selected} className={selected ? "is-selected" : ""} key={service.key} role="option" type="button" onBlur={() => setHoveredService(null)} onClick={() => setServices(toggleValue(services, service.key))} onFocus={() => setHoveredService(service.key)} onMouseEnter={() => setHoveredService(service.key)} onMouseLeave={() => setHoveredService(null)}><span className="audience-opportunity-check">{selected ? <Check size={11} /> : null}</span>{service.label}</button>; })}
            {upcomingServices.length ? <button aria-expanded={upcomingOpen} className="audience-upcoming-toggle" type="button" onClick={() => setUpcomingOpen((open) => !open)}>+{upcomingServices.length} upcoming</button> : null}
            {upcomingOpen ? upcomingServices.map((service) => <button aria-disabled="true" className="is-upcoming" disabled key={service.key} type="button"><span className="audience-opportunity-check" />{service.label}<em>{service.signals.length ? "Preparing data" : "Coming soon"}</em></button>) : null}
          </div>
          <p className="audience-opportunity-help" id="audience-opportunity-help" aria-live="polite">{opportunityHelp}</p>
        </section>

        <section className="audience-advanced-section audience-compact-advanced">
          <button aria-expanded={advancedOpen} className="audience-advanced-toggle" type="button" onClick={() => setAdvancedOpen((open) => !open)}><span><strong>Advanced</strong><small>Folder, batch size, automatic refill, and exclusions</small></span><ChevronDown className={advancedOpen ? "is-open" : ""} size={17} /></button>
          {advancedOpen ? <div className="audience-advanced-fields audience-compact-advanced-fields"><label className="audience-field"><span>Folder</span><select className="audience-input" value={folderId} onChange={(event) => setFolderId(event.target.value)}><option value="">No folder</option>{audienceFolders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select></label><label className="audience-field"><span>First batch</span><select className="audience-input" value={batchSize} onChange={(event) => setBatchSize(Number(event.target.value))}>{(profileOptions?.batch_size_presets || [15, 25, 40]).map((value) => <option key={value} value={value}>{value} leads</option>)}</select></label><label className="audience-field"><span>Refill</span><select className="audience-input" value={refillPolicy} onChange={(event) => setRefillPolicy(event.target.value as Territory["refill_policy"])}><option value="when_depleted">When depleted</option><option value="manual">Manual</option><option value="weekly">Weekly</option><option value="biweekly">Every two weeks</option><option value="monthly">Monthly</option></select></label><p>Always excludes closed businesses and directories.</p></div> : null}
        </section>
      </div>

      <footer className="audience-compact-footer">
        <label className="audience-footer-name"><span>Audience name</span><input aria-label="Audience name" placeholder={generatedName || "Generated after you choose who, where, and why"} type="text" value={name} onChange={(event) => setName(event.target.value)} /><small>{name.trim() ? "Custom name" : "Auto-generated · editable"}</small></label>
        <div className="audience-footer-submit"><p aria-live="polite">{formHint}</p><div>{editing ? <button className="secondary" type="button" onClick={() => setEditing(false)}>Cancel</button> : null}<button className="runbtn audience-create-button" disabled={!valid || saving} type="submit">{saving ? <LoaderCircle className="sl-spin" size={15} /> : null}<span>{mode === "edit" ? "Save audience" : mode === "clone" ? "Create copy" : "Create audience"}</span>{!saving ? <ArrowRight size={15} /> : null}</button></div></div>
      </footer>
    </form>
  </section>;
}

function profilePlace(profile: Territory): PlaceOption | null { if (profile.latitude == null || profile.longitude == null) return null; return { label: profile.place_label || profile.city, provider: profile.place_provider || "stored", external_id: profile.place_external_id, country_code: profile.country_code, latitude: profile.latitude, longitude: profile.longitude }; }
function autoName(nicheLabel: string | undefined, place: PlaceOption | null, radiusKm: number, services: string[], serviceOptions: ProfileOptions["services"]) { const opportunity = serviceOptions.find((service) => service.key === services[0])?.label; return [nicheLabel && place ? `${shortTradeLabel(nicheLabel)} near ${place.label.split(",")[0]}` : nicheLabel ? shortTradeLabel(nicheLabel) : null, place ? `${radiusKm} km` : null, opportunity].filter(Boolean).join(" · "); }
function shortTradeLabel(label: string) { return label.replace(/^home[ -]services?\s+/i, "").replace(/\s+(businesses|companies|contractors|services)$/i, "").trim() || label; }
function toggleValue<T extends string>(values: T[], value: T): T[] { return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]; }
function getFormHint(nicheId: string, place: PlaceOption | null, services: string[]) { if (!nicheId) return "Choose a trade to continue."; if (!place) return "Select and confirm a city to continue."; if (!services.length) return "Choose at least one opportunity to continue."; return "Ready to create."; }
function placeProviderLabel(value: string) { if (value === "google_places") return "Google Places"; if (value === "openstreetmap_nominatim") return "OpenStreetMap"; return "ScoutLead"; }
function batchStateLabel(state?: string) { if (state === "scoring") return "Building"; if (state === "retrying") return "Retrying"; if (state === "ready") return "Ready"; if (state === "partial") return "Partial"; if (state === "empty") return "No matches"; if (state === "failed") return "Needs attention"; return "Set up"; }
function batchStateCopy(batch: ReturnType<typeof useAppData>["profileBatch"]) { if (!batch) return "No lead batch has been generated for this audience yet."; if (["scoring", "retrying"].includes(batch.state)) return "ScoutLead is collecting and evaluating businesses. You can leave this page."; if (["ready", "partial"].includes(batch.state)) return `${batch.remaining_count} leads remain for review.`; if (batch.state === "failed") return "The latest batch could not be completed."; return "No indexed businesses matched this audience."; }
