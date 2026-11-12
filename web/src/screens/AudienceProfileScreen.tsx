import { ArrowRight, Check, ChevronDown, Copy, LoaderCircle, Pencil, Plus, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { LocationCity, LocationCountry, LocationRegion, ProfileCreateInput, ProfileCustomerKind, ProfileExclusion, ProfileOptions, Territory } from "../types/domain";

const SYSTEM_EXCLUSIONS: ProfileExclusion[] = ["closed", "directories"];
const VISIBLE_OPPORTUNITY_KEYS = new Set(["website_availability", "website_upgrade"]);
const MAX_SELECTED_CITIES = 5;
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
  const [countries, setCountries] = useState<LocationCountry[]>([]);
  const [regions, setRegions] = useState<LocationRegion[]>([]);
  const [cities, setCities] = useState<LocationCity[]>([]);
  const [countryCode, setCountryCode] = useState("CA");
  const [regionCode, setRegionCode] = useState("");
  const [selectedCityIds, setSelectedCityIds] = useState<string[]>([]);
  const [cityQuery, setCityQuery] = useState("");
  const [citiesBusy, setCitiesBusy] = useState(false);
  const [customerKinds, setCustomerKinds] = useState<Array<Exclude<ProfileCustomerKind, "both">>>(["residential", "commercial"]);
  const [minGoogleRating, setMinGoogleRating] = useState("4.3");
  const [minReviewCount, setMinReviewCount] = useState("20");
  const [maxReviewCount, setMaxReviewCount] = useState("150");
  const [batchSize, setBatchSize] = useState(25);
  const [refillPolicy, setRefillPolicy] = useState<Territory["refill_policy"]>("when_depleted");
  const [folderId, setFolderId] = useState(defaultFolderId);
  const [services, setServices] = useState<string[]>([]);
  const [hoveredService, setHoveredService] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tradeAddOpen, setTradeAddOpen] = useState(false);
  const [newTrade, setNewTrade] = useState("");
  const [tradeActionBusy, setTradeActionBusy] = useState("");
  const [tradeActionError, setTradeActionError] = useState("");
  const submittingRef = useRef(false);
  const defaultOpportunityAppliedRef = useRef(false);

  useEffect(() => {
    let active = true;
    setOptionsError(false);
    void territoryApi.getProfileOptions().then(
      (options) => { if (active) setProfileOptions(options); },
      () => { if (active) setOptionsError(true); },
    );
    return () => { active = false; };
  }, [territoryApi]);

  const refreshProfileOptions = async () => {
    const options = await territoryApi.getProfileOptions();
    setProfileOptions(options);
    return options;
  };

  const addTrade = async () => {
    const label = newTrade.trim();
    if (!label || tradeActionBusy) return;
    setTradeActionBusy("add");
    setTradeActionError("");
    try {
      const created = await territoryApi.createTrade(label);
      await refreshProfileOptions();
      setNewTrade("");
      setTradeAddOpen(false);
      setNicheId(created.id);
      showToast({ title: `${created.label} added`, tone: "green" });
    } catch (error) {
      setTradeActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setTradeActionBusy("");
    }
  };

  const hideTrade = async (tradeId: string, label: string) => {
    if (tradeActionBusy) return;
    setTradeActionBusy(tradeId);
    setTradeActionError("");
    try {
      await territoryApi.updateTrade(tradeId, { active: false });
      await refreshProfileOptions();
      if (nicheId === tradeId) setNicheId("");
      showToast({ title: `${shortTradeLabel(label)} hidden`, message: "This only changes your trade choices. Existing searches and data remain available.", tone: "green" });
    } catch (error) {
      setTradeActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setTradeActionBusy("");
    }
  };

  useEffect(() => {
    if (mode === "create" && !editing) setFolderId(defaultFolderId);
  }, [defaultFolderId, editing, mode]);

  useEffect(() => {
    let active = true;
    setCitiesBusy(true);
    void Promise.all([
      territoryApi.listLocationCountries(),
      territoryApi.listLocationRegions("CA"),
      territoryApi.listLocationCities("CA"),
    ]).then(([countryOptions, regionOptions, cityOptions]) => {
      if (!active) return;
      setCountries(countryOptions);
      setRegions(regionOptions);
      setCities(cityOptions);
      setSelectedCityIds(cityOptions.slice(0, MAX_SELECTED_CITIES).map((city) => city.id));
    }).catch(() => {
      if (active) setOptionsError(true);
    }).finally(() => {
      if (active) setCitiesBusy(false);
    });
    return () => { active = false; };
  }, [territoryApi]);

  const loadLocationScope = async (nextCountry: string, nextRegion: string, selectedIds?: string[], selectedNames: string[] = []) => {
    setCitiesBusy(true);
    try {
      const [regionOptions, cityOptions] = await Promise.all([
        territoryApi.listLocationRegions(nextCountry),
        territoryApi.listLocationCities(nextCountry, nextRegion || undefined),
      ]);
      setCountryCode(nextCountry);
      setRegionCode(nextRegion);
      setRegions(regionOptions);
      setCities(cityOptions);
      const available = new Set(cityOptions.map((city) => city.id));
      const desiredNames = new Set(selectedNames.map((name) => name.trim().toLowerCase()).filter(Boolean));
      const retained = selectedIds === undefined
        ? cityOptions.slice(0, MAX_SELECTED_CITIES).map((city) => city.id)
        : cityOptions
          .filter((city) => available.has(city.id) && (selectedIds.includes(city.id) || desiredNames.has(city.name.toLowerCase())))
          .slice(0, MAX_SELECTED_CITIES)
          .map((city) => city.id);
      setSelectedCityIds(retained);
      setCityQuery("");
    } catch (error) {
      showToast({ title: "Cities could not be loaded", message: error instanceof Error ? error.message : String(error), tone: "red" });
    } finally {
      setCitiesBusy(false);
    }
  };

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
  const enabledServices = serviceOptions.filter((service) => service.enabled && VISIBLE_OPPORTUNITY_KEYS.has(service.key));
  const enabledServiceKeys = new Set(enabledServices.map((service) => service.key));
  const activeService = serviceOptions.find((service) => service.key === hoveredService);
  const reviewRangeValid = !minReviewCount || !maxReviewCount || Number(minReviewCount) <= Number(maxReviewCount);
  const selectedCities = useMemo(() => { const selected = new Set(selectedCityIds); return cities.filter((city) => selected.has(city.id)); }, [cities, selectedCityIds]);
  const visibleCities = useMemo(() => { const query = cityQuery.trim().toLowerCase(); return query ? cities.filter((city) => `${city.name} ${city.region_name || ""}`.toLowerCase().includes(query)) : cities; }, [cities, cityQuery]);
  const valid = Boolean(selectedProductId && nicheId && selectedCities.length && selectedCities.length <= MAX_SELECTED_CITIES && customerKinds.length && services.length && services.every((service) => enabledServiceKeys.has(service)) && reviewRangeValid);
  const activeBatch = useMemo(() => profileBatch?.audience.id === selectedProfile?.id ? profileBatch : null, [profileBatch, selectedProfile?.id]);

  const toggleCity = (city: LocationCity) => {
    if (selectedCityIds.includes(city.id)) {
      setSelectedCityIds(selectedCityIds.filter((id) => id !== city.id));
      return;
    }
    if (selectedCityIds.length >= MAX_SELECTED_CITIES) {
      showToast({ title: `Choose up to ${MAX_SELECTED_CITIES} cities`, message: "Remove a selected city before adding another.", tone: "red" });
      return;
    }
    setSelectedCityIds([...selectedCityIds, city.id]);
  };

  useEffect(() => {
    if (defaultOpportunityAppliedRef.current || !profileOptions || mode !== "create" || editing) return;
    defaultOpportunityAppliedRef.current = true;
    if (enabledServiceKeys.has("website_availability")) setServices(["website_availability"]);
  }, [editing, enabledServiceKeys, mode, profileOptions]);

  const beginEdit = (nextMode: "edit" | "clone") => {
    if (!selectedProfile) return;
    setMode(nextMode);
    setEditing(true);
    setName(nextMode === "clone" ? `${selectedProfile.label} copy` : selectedProfile.label);
    setNicheId(selectedProfile.niche_id);
    const storedLocations = selectedProfile.locations || [];
    const nextCountry = (storedLocations[0]?.country_code || selectedProfile.country_code || "CA").toUpperCase();
    const nextRegion = storedLocations.length && storedLocations.every((location) => location.region_code === storedLocations[0]?.region_code) ? storedLocations[0]?.region_code || "" : "";
    void loadLocationScope(
      nextCountry,
      nextRegion,
      storedLocations.map((location) => location.id),
      storedLocations.length ? storedLocations.map((location) => location.city) : [selectedProfile.city],
    );
    setCustomerKinds(selectedProfile.customer_kind === "both" ? ["residential", "commercial"] : [selectedProfile.customer_kind]);
    setMinGoogleRating(optionalNumberInput(selectedProfile.min_google_rating));
    setMinReviewCount(optionalNumberInput(selectedProfile.min_review_count));
    setMaxReviewCount(optionalNumberInput(selectedProfile.max_review_count));
    setBatchSize(selectedProfile.batch_size);
    setRefillPolicy(selectedProfile.refill_policy);
    setFolderId(selectedProfile.folder_id || "");
    setServices(selectedProfile.service_keys);
  };

  if (selectedProfile && !editing) {
    const scoring = activeBatch?.state === "scoring" || activeBatch?.state === "retrying";
    return <section className="audience-status-screen">
      <header className="audience-page-heading audience-status-heading"><div><span>Saved search</span><h1>{selectedProfile.label}</h1><p>{selectedProfile.niche_label || "Local businesses"} · {profileLocationSummary(selectedProfile)}</p></div><div className="audience-status-actions"><button className="secondary" type="button" onClick={() => beginEdit("clone")}><Copy size={14} /> Copy</button><button className="secondary" type="button" onClick={() => beginEdit("edit")}><Pencil size={14} /> Edit</button></div></header>
      <div className="audience-status-panel"><span className={`audience-state is-${activeBatch?.state || "setup"}`}>{scoring ? <LoaderCircle className="sl-spin" size={15} /> : <Check size={15} />}{batchStateLabel(activeBatch?.state)}</span><strong>{activeBatch?.result_count || 0} leads in the current batch</strong><p>{batchStateCopy(activeBatch)}</p></div>
    </section>;
  }

  const submit = async () => {
    if (!valid || !selectedCities.length || submittingRef.current) return;
    submittingRef.current = true;
    setSaving(true);
    const fitFilters = {
      customer_kind: customerKinds.length === 2 ? "both" as const : customerKinds[0] || "both",
      min_google_rating: optionalNumber(minGoogleRating),
      min_review_count: optionalNumber(minReviewCount),
      max_review_count: optionalNumber(maxReviewCount),
    };
    const markets = selectedCities.map((city) => ({ city: city.name, place_label: city.label, place_provider: "geonames", place_external_id: city.id, country_code: city.country_code, region_code: city.region_code, region_name: city.region_name, latitude: city.latitude, longitude: city.longitude }));
    try {
      if (mode === "edit" && selectedProfile) {
        await updateProfile(selectedProfile.id, { label: name.trim() || autoName(selectedNiche?.label, selectedCities, services, serviceOptions), folder_id: folderId || null, niche_id: nicheId, ...fitFilters, locations: markets.map((market) => ({ id: market.place_external_id, city: market.city, label: market.place_label, provider: market.place_provider, external_id: market.place_external_id, country_code: market.country_code, region_code: market.region_code, region_name: market.region_name, latitude: market.latitude, longitude: market.longitude })), service_keys: services, batch_size: batchSize, refill_policy: refillPolicy, exclusion_keys: SYSTEM_EXCLUSIONS });
        setEditing(false);
        showToast({ title: "Search updated", message: "New criteria will apply to the next batch.", tone: "green" });
      } else {
        const input: ProfileCreateInput = { product_id: selectedProductId, folder_id: folderId || null, name: name.trim() || autoName(selectedNiche?.label, selectedCities, services, serviceOptions), niche_id: nicheId, ...fitFilters, markets, services, signals: [], exclude: SYSTEM_EXCLUSIONS, limit: batchSize, refill_policy: refillPolicy, exclude_already_delivered: true, ...(mode === "clone" && selectedProfile ? { clone_from_id: selectedProfile.id } : {}) };
        await createProfile(input);
        setEditing(false);
        setMode("create");
        showToast({ title: mode === "clone" ? "Search copied" : "Search ready", message: "The initial lead batch is queued.", tone: "green" });
      }
    } catch (error) {
      showToast({ title: "Search could not be saved", message: error instanceof Error ? error.message : String(error), tone: "red" });
    } finally {
      submittingRef.current = false;
      setSaving(false);
    }
  };

  const formHint = getFormHint(nicheId, selectedCities.length, customerKinds.length, services, reviewRangeValid);
  const generatedName = autoName(selectedNiche?.label, selectedCities, services, serviceOptions);
  const opportunityHelp = activeService ? opportunityDescription(activeService.key, activeService.description)
    : services.length ? `${services.length} selected — leads must match at least one website outcome.` : "Choose whether to find businesses with no website, a website that needs improvement, or both.";

  return <section className="audience-setup-screen audience-compact-screen">
    <header className="audience-page-heading audience-compact-heading"><div><span>{selectedProduct?.product_name || "Lead discovery"}</span><h1>{mode === "edit" ? "Edit lead search" : mode === "clone" ? "Copy lead search" : "Create a lead search"}</h1><p>Choose a trade, location, and website opportunity.</p></div></header>
    <form className="audience-compact-form" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <div className="audience-compact-card">
        <section className="audience-compact-section" aria-labelledby="audience-trade-title">
          <header className="audience-section-heading"><span>01</span><h2 id="audience-trade-title">Who you’re targeting</h2></header>
          <div className="audience-compact-field">
            {showTradeSearch ? <label htmlFor="audience-trade-search">Trade</label> : <span className="audience-compact-label">Trade</span>}
            {showTradeSearch ? <div className="audience-trade-search"><Search aria-hidden="true" size={14} /><input autoComplete="off" id="audience-trade-search" placeholder="Search trades…" type="search" value={tradeQuery} onChange={(event) => setTradeQuery(event.target.value)} /></div> : null}
            <div className="audience-trade-chips" role="group" aria-label="Trade">
              {visibleBusinessTypes.map((businessType) => <div className={`audience-trade-chip${nicheId === businessType.id ? " is-selected" : ""}`} key={businessType.id}><button aria-pressed={nicheId === businessType.id} className="audience-trade-select" disabled={tradeActionBusy === businessType.id} type="button" onClick={() => setNicheId(businessType.id)}>{nicheId === businessType.id ? <Check size={13} /> : null}{shortTradeLabel(businessType.label)}</button><button aria-label={`Hide ${shortTradeLabel(businessType.label)} from my trades`} className="audience-trade-hide" disabled={Boolean(tradeActionBusy)} title="Hide from my trades" type="button" onClick={() => void hideTrade(businessType.id, businessType.label)}>{tradeActionBusy === businessType.id ? <LoaderCircle className="sl-spin" size={12} /> : <X size={12} />}</button></div>)}
              {tradeAddOpen ? <div className="audience-trade-add-inline"><input aria-label="New trade name" autoFocus placeholder="Add a trade" size={Math.max(10, Math.min(22, newTrade.length + 2))} value={newTrade} onChange={(event) => setNewTrade(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void addTrade(); } if (event.key === "Escape") { setTradeAddOpen(false); setNewTrade(""); } }} /><button aria-label="Add trade" disabled={!newTrade.trim() || Boolean(tradeActionBusy)} type="button" onClick={() => void addTrade()}>{tradeActionBusy === "add" ? <LoaderCircle className="sl-spin" size={13} /> : <Check size={13} />}</button><button aria-label="Cancel adding trade" disabled={Boolean(tradeActionBusy)} type="button" onClick={() => { setTradeAddOpen(false); setNewTrade(""); }}><X size={13} /></button></div> : <button aria-label="Add trade" className="audience-trade-add" title="Add trade" type="button" onClick={() => { setTradeAddOpen(true); setTradeActionError(""); }}><Plus size={15} /></button>}
            </div>
            {tradeActionError ? <p className="audience-row-error">{tradeActionError}</p> : null}
            {!profileOptions && !optionsError ? <p className="audience-row-status"><LoaderCircle className="sl-spin" size={14} />Loading trades</p> : null}
            {profileOptions && !visibleBusinessTypes.length ? <p className="audience-empty-options">No trades match “{tradeQuery}”.</p> : null}
            {optionsError ? <p className="audience-row-error">Trades are unavailable.</p> : null}
          </div>
          <div className="audience-targeting-filters">
            <fieldset className="audience-customer-kind">
              <legend>Customer type</legend>
              <div className="audience-customer-options">
                {(["residential", "commercial"] as const).map((value) => <label key={value}><input checked={customerKinds.includes(value)} type="checkbox" value={value} onChange={() => setCustomerKinds(toggleValue(customerKinds, value))} /><span>{value[0].toUpperCase() + value.slice(1)}</span></label>)}
              </div>
            </fieldset>
            <fieldset className="audience-google-filters">
              <label><span><i aria-hidden="true">G</i> Rating</span><input aria-label="Minimum Google rating" inputMode="decimal" max="5" min="0" step="0.1" type="number" value={minGoogleRating} onChange={(event) => setMinGoogleRating(event.target.value)} /></label>
              <label><span><i aria-hidden="true">G</i> Reviews</span><div className="audience-number-range"><input aria-label="Minimum Google review count" inputMode="numeric" min="0" step="1" type="number" value={minReviewCount} onChange={(event) => setMinReviewCount(event.target.value)} /><span>to</span><input aria-label="Maximum Google review count" inputMode="numeric" min="0" step="1" type="number" value={maxReviewCount} onChange={(event) => setMaxReviewCount(event.target.value)} /></div></label>
            </fieldset>
          </div>
        </section>

        <section className="audience-compact-section" aria-labelledby="audience-market-title">
          <header className="audience-section-heading"><span>02</span><h2 id="audience-market-title">Where to search</h2></header>
          <div className="audience-compact-field audience-location-field audience-location-scope">
            <div className="audience-location-selects">
              <label><span>Country</span><select value={countryCode} onChange={(event) => void loadLocationScope(event.target.value, "")}>
                {countries.map((country) => <option key={country.code} value={country.code}>{country.name}</option>)}
              </select></label>
              <label><span>Province or state</span><select value={regionCode} onChange={(event) => void loadLocationScope(countryCode, event.target.value)}>
                <option value="">All {countryCode === "CA" ? "provinces and territories" : countryCode === "US" ? "states" : "regions"}</option>
                {regions.map((region) => <option key={region.code} value={region.code}>{region.name}</option>)}
              </select></label>
            </div>
            <div className="audience-city-toolbar">
              <label className="audience-city-search"><Search aria-hidden="true" size={14} /><input aria-label="Filter cities" placeholder="Filter cities" type="search" value={cityQuery} onChange={(event) => setCityQuery(event.target.value)} /></label>
              <strong>{selectedCities.length} of {MAX_SELECTED_CITIES} selected</strong>
              <button type="button" onClick={() => setSelectedCityIds(cities.slice(0, MAX_SELECTED_CITIES).map((city) => city.id))}>Use top 5</button>
              <button type="button" onClick={() => setSelectedCityIds([])}>Clear</button>
            </div>
            {selectedCities.length ? <div className="audience-selected-cities" aria-label="Selected cities">
              {selectedCities.map((city) => <button aria-label={`Remove ${city.name}`} key={city.id} title={`Remove ${city.name}`} type="button" onClick={() => toggleCity(city)}><span>{city.name}</span><X size={12} /></button>)}
            </div> : null}
            <div className="audience-city-list" role="group" aria-label="Cities to search">
              {citiesBusy ? <p className="audience-row-status"><LoaderCircle className="sl-spin" size={14} />Loading cities</p> : null}
              {!citiesBusy && visibleCities.map((city) => { const selected = selectedCityIds.includes(city.id); const unavailable = !selected && selectedCityIds.length >= MAX_SELECTED_CITIES; return <label className={`${selected ? "is-selected" : ""}${unavailable ? " is-unavailable" : ""}`} key={city.id}><input checked={selected} disabled={unavailable} type="checkbox" onChange={() => toggleCity(city)} /><span><strong>{city.name}</strong>{city.region_name ? <small>{city.region_name}</small> : null}</span>{selected ? <Check size={13} /> : null}</label>; })}
              {!citiesBusy && !visibleCities.length ? <p className="audience-empty-options">No cities match “{cityQuery}”.</p> : null}
            </div>
            <p className="audience-field-help">Choose up to five cities. Collection runs in the background, one city at a time, and results appear as each city completes.</p>
          </div>
        </section>

        <section className="audience-compact-section" aria-labelledby="audience-signals-title">
          <header className="audience-section-heading"><span>03</span><h2 id="audience-signals-title">Website opportunity</h2><small>Choose one or both</small></header>
          <div className="audience-opportunity-chips" role="group" aria-describedby="audience-opportunity-help" aria-label="Website opportunities">
            {enabledServices.map((service) => { const selected = services.includes(service.key); return <button aria-pressed={selected} className={selected ? "is-selected" : ""} key={service.key} type="button" onBlur={() => setHoveredService(null)} onClick={() => setServices(toggleValue(services, service.key))} onFocus={() => setHoveredService(service.key)} onMouseEnter={() => setHoveredService(service.key)} onMouseLeave={() => setHoveredService(null)}>{selected ? <Check aria-hidden="true" size={13} /> : null}{opportunityLabel(service.key, service.label)}</button>; })}
          </div>
          <p className="audience-opportunity-help" id="audience-opportunity-help" aria-live="polite">{opportunityHelp}</p>
        </section>

        <section className="audience-advanced-section audience-compact-advanced">
          <button aria-expanded={advancedOpen} className="audience-advanced-toggle" type="button" onClick={() => setAdvancedOpen((open) => !open)}><span><strong>Advanced</strong><small>Folder, batch size, automatic refill, and exclusions</small></span><ChevronDown className={advancedOpen ? "is-open" : ""} size={17} /></button>
          {advancedOpen ? <div className="audience-advanced-fields audience-compact-advanced-fields"><label className="audience-field"><span>Folder</span><select className="audience-input" value={folderId} onChange={(event) => setFolderId(event.target.value)}><option value="">Automatic by trade</option>{audienceFolders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select></label><label className="audience-field"><span>First batch</span><select className="audience-input" value={batchSize} onChange={(event) => setBatchSize(Number(event.target.value))}>{(profileOptions?.batch_size_presets || [15, 25, 40]).map((value) => <option key={value} value={value}>{value} leads</option>)}</select></label><label className="audience-field"><span>Refill</span><select className="audience-input" value={refillPolicy} onChange={(event) => setRefillPolicy(event.target.value as Territory["refill_policy"])}><option value="when_depleted">When depleted</option><option value="manual">Manual</option><option value="weekly">Weekly</option><option value="biweekly">Every two weeks</option><option value="monthly">Monthly</option></select></label><p>Always excludes closed businesses and directories.</p></div> : null}
        </section>
      </div>

      <footer className="audience-compact-footer">
        <label className="audience-footer-name"><span>Search name</span><input aria-label="Search name" placeholder={generatedName || "Generated after you choose who, where, and why"} type="text" value={name} onChange={(event) => setName(event.target.value)} /><small>{name.trim() ? "Custom name" : "Auto-generated · editable"}</small></label>
        <div className="audience-footer-submit"><p aria-live="polite">{formHint}</p><div>{editing ? <button className="secondary" type="button" onClick={() => setEditing(false)}>Cancel</button> : null}<button className="runbtn audience-create-button" disabled={!valid || saving} type="submit">{saving ? <LoaderCircle className="sl-spin" size={15} /> : null}<span>{mode === "edit" ? "Save search" : mode === "clone" ? "Create copy" : "Find leads"}</span>{!saving ? <ArrowRight size={15} /> : null}</button></div></div>
      </footer>
    </form>
  </section>;
}

function autoName(nicheLabel: string | undefined, cities: LocationCity[], services: string[], serviceOptions: ProfileOptions["services"]) { const selected = serviceOptions.filter((service) => services.includes(service.key)); const opportunity = selected.length > 1 ? "Website opportunities" : selected[0] ? opportunityLabel(selected[0].key, selected[0].label) : null; const location = cities.length === 1 ? cities[0].name : cities.length > 1 ? `${cities.length} cities` : null; return [nicheLabel && location ? `${shortTradeLabel(nicheLabel)} in ${location}` : nicheLabel ? shortTradeLabel(nicheLabel) : null, opportunity].filter(Boolean).join(" · "); }
function opportunityLabel(key: string, fallback: string) { if (key === "website_availability") return "No website"; if (key === "website_upgrade") return "Website needs improvement"; return fallback; }
function opportunityDescription(key: string, fallback?: string | null) { if (key === "website_availability") return "Find active businesses without a verified owned website."; if (key === "website_upgrade") return "Find websites with measured technical, mobile, or customer-conversion gaps."; return fallback || "Find businesses that match this website opportunity."; }
function shortTradeLabel(label: string) {
  const shortened = label
    .replace(/^home[ -]services?\s+/i, "")
    .replace(/\s+(businesses|companies|contractors|services)$/i, "")
    .trim() || label;
  return shortened.replace(/\bhvac\b/gi, "HVAC");
}
function toggleValue<T extends string>(values: T[], value: T): T[] { return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]; }
function getFormHint(nicheId: string, cityCount: number, customerKindCount: number, services: string[], reviewRangeValid: boolean) { if (!nicheId) return "Choose a trade to continue."; if (!customerKindCount) return "Choose at least one customer type."; if (!cityCount) return "Select at least one city to continue."; if (cityCount > MAX_SELECTED_CITIES) return `Choose no more than ${MAX_SELECTED_CITIES} cities.`; if (!services.length) return "Choose a website opportunity to continue."; if (!reviewRangeValid) return "Minimum reviews cannot exceed maximum reviews."; return `Ready to collect ${cityCount} ${cityCount === 1 ? "city" : "cities"} in the background.`; }
function optionalNumber(value: string): number | null { return value.trim() === "" ? null : Number(value); }
function optionalNumberInput(value?: number | null): string { return value == null ? "" : String(value); }
function profileLocationSummary(profile: Territory) { const locations = profile.locations || []; if (locations.length === 1) return locations[0].label || locations[0].city; if (locations.length > 1) return `${locations.length} cities`; return `${profile.place_label || profile.city} · ${profile.radius_km} km`; }
function batchStateLabel(state?: string) { if (state === "scoring") return "Building"; if (state === "retrying") return "Retrying"; if (state === "ready") return "Ready"; if (state === "partial") return "Partial"; if (state === "empty") return "No matches"; if (state === "failed") return "Needs attention"; return "Set up"; }
function batchStateCopy(batch: ReturnType<typeof useAppData>["profileBatch"]) { if (!batch) return "No lead batch has been generated for this saved search yet."; const progress = batch.location_count && batch.location_count > 1 ? ` ${batch.locations_completed || 0} of ${batch.location_count} cities completed.` : ""; if (["scoring", "retrying"].includes(batch.state)) return `ScoutLead is collecting and evaluating businesses. You can leave this page.${progress}`; if (["ready", "partial"].includes(batch.state)) return `${batch.remaining_count} leads remain for review.${progress}`; if (batch.state === "failed") return `The latest batch could not be completed.${progress}`; return "No indexed businesses matched this search."; }
