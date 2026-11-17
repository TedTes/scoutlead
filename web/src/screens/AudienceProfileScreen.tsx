import { ArrowRight, Check, ChevronDown, Copy, LoaderCircle, Pencil, Plus, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import { useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { LocationCity, LocationCountry, LocationRegion, ProfileCreateInput, ProfileCustomerKind, ProfileExclusion, ProfileOptions, Territory } from "../types/domain";

const SYSTEM_EXCLUSIONS: ProfileExclusion[] = ["closed", "directories"];
const VISIBLE_OPPORTUNITY_KEYS = new Set(["website_availability", "website_upgrade"]);
const MAX_SELECTED_CITIES = 5;
const MIN_GOOGLE_RATING = 0;
const MAX_GOOGLE_RATING = 5;
const MIN_GOOGLE_REVIEWS = 0;
const MAX_GOOGLE_REVIEWS = 500;
type FormMode = "create" | "edit" | "clone";

export function AudienceProfileScreen({ defaultFolderId = "" }: { defaultFolderId?: string }) {
  const { audienceFolders, createProfile, updateProfile, profileBatch, selectedProductId, selectedProfile, territoryApi } = useAppData();
  const { showToast } = useToast();
  const [profileOptions, setProfileOptions] = useState<ProfileOptions | null>(null);
  const [optionsError, setOptionsError] = useState(false);
  const [mode, setMode] = useState<FormMode>("create");
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [nicheId, setNicheId] = useState("");
  const [tradeQuery, setTradeQuery] = useState("");
  const [tradeSearchOpen, setTradeSearchOpen] = useState(false);
  const [countries, setCountries] = useState<LocationCountry[]>([]);
  const [regions, setRegions] = useState<LocationRegion[]>([]);
  const [cities, setCities] = useState<LocationCity[]>([]);
  const [countryCode, setCountryCode] = useState("CA");
  const [regionCode, setRegionCode] = useState("");
  const [selectedCityIds, setSelectedCityIds] = useState<string[]>([]);
  const [cityQuery, setCityQuery] = useState("");
  const [citiesBusy, setCitiesBusy] = useState(false);
  const [customerKinds, setCustomerKinds] = useState<Array<Exclude<ProfileCustomerKind, "both">>>(["residential", "commercial"]);
  const [minGoogleRating, setMinGoogleRating] = useState(String(MIN_GOOGLE_RATING));
  const [maxGoogleRating, setMaxGoogleRating] = useState(String(MAX_GOOGLE_RATING));
  const [minReviewCount, setMinReviewCount] = useState(String(MIN_GOOGLE_REVIEWS));
  const [maxReviewCount, setMaxReviewCount] = useState(String(MAX_GOOGLE_REVIEWS));
  const [batchSize, setBatchSize] = useState(25);
  const [refillPolicy, setRefillPolicy] = useState<Territory["refill_policy"]>("when_depleted");
  const [folderId, setFolderId] = useState(defaultFolderId);
  const [services, setServices] = useState<string[]>([]);
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
  const canSearchTrades = businessTypes.length > 12;
  const visibleBusinessTypes = useMemo(() => {
    const query = tradeSearchOpen ? tradeQuery.trim().toLowerCase() : "";
    return query
      ? businessTypes.filter((option) => `${option.label} ${option.category || ""}`.toLowerCase().includes(query))
      : businessTypes;
  }, [businessTypes, tradeSearchOpen, tradeQuery]);
  const serviceOptions = profileOptions?.services || [];
  const enabledServices = serviceOptions.filter((service) => service.enabled && VISIBLE_OPPORTUNITY_KEYS.has(service.key));
  const enabledServiceKeys = new Set(enabledServices.map((service) => service.key));
  const ratingRangeValid = Number(minGoogleRating) <= Number(maxGoogleRating);
  const reviewRangeValid = Number(minReviewCount) <= Number(maxReviewCount);
  const selectedCities = useMemo(() => { const selected = new Set(selectedCityIds); return cities.filter((city) => selected.has(city.id)); }, [cities, selectedCityIds]);
  const visibleCities = useMemo(() => { const query = cityQuery.trim().toLowerCase(); return query ? cities.filter((city) => `${city.name} ${city.region_name || ""}`.toLowerCase().includes(query)) : cities; }, [cities, cityQuery]);
  const citySearchResults = useMemo(() => {
    if (!cityQuery.trim() || selectedCityIds.length >= MAX_SELECTED_CITIES) return [];
    const selected = new Set(selectedCityIds);
    return visibleCities.filter((city) => !selected.has(city.id));
  }, [cityQuery, selectedCityIds, visibleCities]);
  const valid = Boolean(selectedProductId && nicheId && selectedCities.length && selectedCities.length <= MAX_SELECTED_CITIES && customerKinds.length && services.length && services.every((service) => enabledServiceKeys.has(service)) && ratingRangeValid && reviewRangeValid);
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
    setMinGoogleRating(optionalNumberInput(selectedProfile.min_google_rating, MIN_GOOGLE_RATING));
    setMaxGoogleRating(optionalNumberInput(selectedProfile.max_google_rating, MAX_GOOGLE_RATING));
    setMinReviewCount(optionalNumberInput(selectedProfile.min_review_count, MIN_GOOGLE_REVIEWS));
    setMaxReviewCount(optionalNumberInput(selectedProfile.max_review_count, MAX_GOOGLE_REVIEWS));
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
      min_google_rating: boundedMinimum(minGoogleRating, MIN_GOOGLE_RATING),
      max_google_rating: boundedMaximum(maxGoogleRating, MAX_GOOGLE_RATING),
      min_review_count: boundedMinimum(minReviewCount, MIN_GOOGLE_REVIEWS),
      max_review_count: boundedMaximum(maxReviewCount, MAX_GOOGLE_REVIEWS),
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
        showToast({ title: mode === "clone" ? "Search copied" : "Search ready", message: "Matching leads are ready to review.", tone: "green" });
      }
    } catch (error) {
      showToast({ title: "Search could not be saved", message: error instanceof Error ? error.message : String(error), tone: "red" });
    } finally {
      submittingRef.current = false;
      setSaving(false);
    }
  };

  const formHint = getFormHint(nicheId, selectedCities.length, customerKinds.length, services, ratingRangeValid, reviewRangeValid);
  const generatedName = autoName(selectedNiche?.label, selectedCities, services, serviceOptions);

  return <section className="audience-setup-screen audience-compact-screen">
    <form className="audience-compact-form" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <div className="audience-compact-card">
        <section className="audience-compact-section" aria-labelledby="audience-trade-title">
          <header className="audience-section-heading"><span>01</span><h2 id="audience-trade-title">Trade</h2></header>
          <div className="audience-compact-field">
            {tradeSearchOpen ? <div className="audience-trade-search"><Search aria-hidden="true" size={14} /><input autoComplete="off" autoFocus id="audience-trade-search" placeholder="Search trades…" type="search" value={tradeQuery} onChange={(event) => setTradeQuery(event.target.value)} /><button aria-label="Close trade search" type="button" onClick={() => { setTradeSearchOpen(false); setTradeQuery(""); }}><X size={13} /></button></div> : null}
            <div className="audience-trade-chips" role="group" aria-label="Trade">
              {visibleBusinessTypes.map((businessType) => <div className={`audience-trade-chip${nicheId === businessType.id ? " is-selected" : ""}`} key={businessType.id}><button aria-pressed={nicheId === businessType.id} className="audience-trade-select" disabled={tradeActionBusy === businessType.id} type="button" onClick={() => setNicheId(businessType.id)}>{nicheId === businessType.id ? <Check size={13} /> : null}{shortTradeLabel(businessType.label)}</button><button aria-label={`Hide ${shortTradeLabel(businessType.label)} from my trades`} className="audience-trade-hide" disabled={Boolean(tradeActionBusy)} title="Hide from my trades" type="button" onClick={() => void hideTrade(businessType.id, businessType.label)}>{tradeActionBusy === businessType.id ? <LoaderCircle className="sl-spin" size={12} /> : <X size={12} />}</button></div>)}
              {canSearchTrades && !tradeSearchOpen ? <button aria-label="Search trades" className="audience-trade-add audience-trade-search-toggle" title="Search trades" type="button" onClick={() => setTradeSearchOpen(true)}><Search size={14} /></button> : null}
              {tradeAddOpen ? <div className="audience-trade-add-inline"><input aria-label="New trade name" autoFocus placeholder="Add a trade" size={Math.max(10, Math.min(22, newTrade.length + 2))} value={newTrade} onChange={(event) => setNewTrade(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void addTrade(); } if (event.key === "Escape") { setTradeAddOpen(false); setNewTrade(""); } }} /><button aria-label="Add trade" disabled={!newTrade.trim() || Boolean(tradeActionBusy)} type="button" onClick={() => void addTrade()}>{tradeActionBusy === "add" ? <LoaderCircle className="sl-spin" size={13} /> : <Check size={13} />}</button><button aria-label="Cancel adding trade" disabled={Boolean(tradeActionBusy)} type="button" onClick={() => { setTradeAddOpen(false); setNewTrade(""); }}><X size={13} /></button></div> : <button aria-label="Add trade" className="audience-trade-add" title="Add trade" type="button" onClick={() => { setTradeAddOpen(true); setTradeActionError(""); }}><Plus size={15} /></button>}
            </div>
            {tradeActionError ? <p className="audience-row-error">{tradeActionError}</p> : null}
            {!profileOptions && !optionsError ? <p className="audience-row-status"><LoaderCircle className="sl-spin" size={14} />Loading trades</p> : null}
            {profileOptions && !visibleBusinessTypes.length ? <p className="audience-empty-options">No trades match “{tradeQuery}”.</p> : null}
            {optionsError ? <p className="audience-row-error">Trades are unavailable.</p> : null}
          </div>
        </section>

        <section className="audience-compact-section" aria-labelledby="audience-market-title">
          <header className="audience-section-heading"><span>02</span><h2 id="audience-market-title">Places</h2></header>
          <div className="audience-compact-field audience-location-field audience-location-scope">
            <div className="audience-location-controls">
              <label><span>Country</span><select value={countryCode} onChange={(event) => void loadLocationScope(event.target.value, "")}>
                {countries.map((country) => <option key={country.code} value={country.code}>{country.name}</option>)}
              </select></label>
              <label><span>Province or state</span><select value={regionCode} onChange={(event) => void loadLocationScope(countryCode, event.target.value)}>
                <option value="">All {countryCode === "CA" ? "provinces and territories" : countryCode === "US" ? "states" : "regions"}</option>
                {regions.map((region) => <option key={region.code} value={region.code}>{region.name}</option>)}
              </select></label>
              <div className="audience-city-toolbar">
                {selectedCityIds.length < MAX_SELECTED_CITIES || cityQuery ? <label className="audience-city-search"><Search aria-hidden="true" size={14} /><input aria-label="Search cities to add" placeholder="Search cities to add" type="search" value={cityQuery} onChange={(event) => setCityQuery(event.target.value)} /></label> : null}
                <strong>{selectedCities.length} selected</strong>
                {selectedCities.length ? <button type="button" onClick={() => setSelectedCityIds([])}>Clear</button> : null}
              </div>
            </div>
            {selectedCities.length ? <div className="audience-selected-cities" aria-label="Selected cities">
              {selectedCities.map((city) => <button aria-label={`Remove ${city.name}`} key={city.id} title={`Remove ${city.name}`} type="button" onClick={() => toggleCity(city)}><span>{city.name}</span><X size={12} /></button>)}
            </div> : null}
            {citiesBusy ? <p className="audience-row-status"><LoaderCircle className="sl-spin" size={14} />Loading cities</p> : null}
            {!citiesBusy && cityQuery.trim() && selectedCityIds.length < MAX_SELECTED_CITIES ? <div className="audience-city-results" aria-label="City search results">
              {citySearchResults.map((city) => <button key={city.id} type="button" onClick={() => { toggleCity(city); setCityQuery(""); }}><span><strong>{city.name}</strong>{city.region_name ? <small>{city.region_name}</small> : null}</span><Plus aria-hidden="true" size={14} /></button>)}
              {!citySearchResults.length ? <p className="audience-empty-options">No additional cities match “{cityQuery}”.</p> : null}
            </div> : null}
            {!citiesBusy && cityQuery.trim() && selectedCityIds.length >= MAX_SELECTED_CITIES ? <p className="audience-city-limit">Remove a selected city before adding another.</p> : null}
          </div>
        </section>

        <div className="audience-compact-section audience-bottom-criteria">
          <section className="audience-inline-criteria" aria-labelledby="audience-customer-title">
            <header className="audience-section-heading"><span>03</span><h2 id="audience-customer-title">Customer type</h2></header>
            <div className="audience-customer-kind" role="group" aria-labelledby="audience-customer-title">
              <div className="audience-customer-options">
                {(["residential", "commercial"] as const).map((value) => <label key={value}><input checked={customerKinds.includes(value)} type="checkbox" value={value} onChange={() => setCustomerKinds(toggleValue(customerKinds, value))} /><span>{value[0].toUpperCase() + value.slice(1)}</span></label>)}
              </div>
            </div>
          </section>
          <section className="audience-inline-criteria" aria-labelledby="audience-status-title">
            <header className="audience-section-heading"><span>04</span><h2 id="audience-status-title">Website status</h2></header>
            <div className="audience-website-opportunity" role="group" aria-labelledby="audience-status-title">
              <div className="audience-opportunity-options">
                {enabledServices.map((service) => <label key={service.key}><input checked={services.includes(service.key)} type="checkbox" value={service.key} onChange={() => setServices(toggleValue(services, service.key))} /><span>{opportunityLabel(service.key, service.label)}</span></label>)}
              </div>
            </div>
          </section>
          <section className="audience-inline-criteria" aria-labelledby="audience-rating-title">
            <header className="audience-section-heading"><span>05</span><h2 id="audience-rating-title">Rating</h2></header>
            <DualRangeFilter label="Rating" hideLabel min={MIN_GOOGLE_RATING} max={MAX_GOOGLE_RATING} step={0.1} minimum={Number(minGoogleRating)} maximum={Number(maxGoogleRating)} format={(value) => value.toFixed(1)} onMinimumChange={(value) => setMinGoogleRating(String(value))} onMaximumChange={(value) => setMaxGoogleRating(String(value))} />
          </section>
          <section className="audience-inline-criteria" aria-labelledby="audience-reviews-title">
            <header className="audience-section-heading"><span>06</span><h2 id="audience-reviews-title">Reviews</h2></header>
            <DualRangeFilter label="Reviews" hideLabel min={MIN_GOOGLE_REVIEWS} max={MAX_GOOGLE_REVIEWS} step={1} minimum={Number(minReviewCount)} maximum={Number(maxReviewCount)} format={(value) => value === MAX_GOOGLE_REVIEWS ? `${value}+` : String(value)} onMinimumChange={(value) => setMinReviewCount(String(value))} onMaximumChange={(value) => setMaxReviewCount(String(value))} />
          </section>
        </div>

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

function DualRangeFilter({
  label,
  hideLabel = false,
  min,
  max,
  step,
  minimum,
  maximum,
  format,
  onMinimumChange,
  onMaximumChange,
}: {
  label: string;
  hideLabel?: boolean;
  min: number;
  max: number;
  step: number;
  minimum: number;
  maximum: number;
  format: (value: number) => string;
  onMinimumChange: (value: number) => void;
  onMaximumChange: (value: number) => void;
}) {
  const span = max - min;
  const start = ((minimum - min) / span) * 100;
  const end = ((maximum - min) / span) * 100;
  const style = {
    "--range-start": `${start}%`,
    "--range-end": `${end}%`,
  } as CSSProperties;
  return <label className="audience-range-filter">
    <span className={`audience-range-heading${hideLabel ? " is-values-only" : ""}`}>{!hideLabel ? <span><i aria-hidden="true">G</i>{label}</span> : null}<span className="audience-range-values"><output>{format(minimum)}</output><small>to</small><output>{format(maximum)}</output></span></span>
    <span className="audience-dual-range" style={style}>
      <span aria-hidden="true" className="audience-dual-range-track" />
      <input aria-label={`Minimum Google ${label.toLowerCase()}`} className="is-minimum" max={max} min={min} step={step} type="range" value={minimum} onChange={(event) => onMinimumChange(Math.min(Number(event.target.value), maximum))} />
      <input aria-label={`Maximum Google ${label.toLowerCase()}`} className="is-maximum" max={max} min={min} step={step} type="range" value={maximum} onChange={(event) => onMaximumChange(Math.max(Number(event.target.value), minimum))} />
    </span>
  </label>;
}

function autoName(nicheLabel: string | undefined, cities: LocationCity[], services: string[], serviceOptions: ProfileOptions["services"]) { const selected = serviceOptions.filter((service) => services.includes(service.key)); const opportunity = selected.length > 1 ? "Website opportunities" : selected[0] ? opportunityLabel(selected[0].key, selected[0].label) : null; const location = cities.length === 1 ? cities[0].name : cities.length > 1 ? `${cities.length} cities` : null; return [nicheLabel && location ? `${shortTradeLabel(nicheLabel)} in ${location}` : nicheLabel ? shortTradeLabel(nicheLabel) : null, opportunity].filter(Boolean).join(" · "); }
function opportunityLabel(key: string, fallback: string) { if (key === "website_availability") return "No website"; if (key === "website_upgrade") return "Website needs improvement"; return fallback; }
function shortTradeLabel(label: string) {
  const shortened = label
    .replace(/^home[ -]services?\s+/i, "")
    .replace(/\s+(businesses|companies|contractors|services)$/i, "")
    .trim() || label;
  return shortened.replace(/\bhvac\b/gi, "HVAC");
}
function toggleValue<T extends string>(values: T[], value: T): T[] { return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]; }
function getFormHint(nicheId: string, cityCount: number, customerKindCount: number, services: string[], ratingRangeValid: boolean, reviewRangeValid: boolean) { if (!nicheId) return "Choose a trade to continue."; if (!customerKindCount) return "Choose at least one customer type."; if (!cityCount) return "Select at least one city to continue."; if (cityCount > MAX_SELECTED_CITIES) return `Choose no more than ${MAX_SELECTED_CITIES} cities.`; if (!services.length) return "Choose a website opportunity to continue."; if (!ratingRangeValid) return "Minimum rating cannot exceed maximum rating."; if (!reviewRangeValid) return "Minimum reviews cannot exceed maximum reviews."; return `Ready to collect ${cityCount} ${cityCount === 1 ? "city" : "cities"} in the background.`; }
function boundedMinimum(value: string, lowerBound: number): number | null { const parsed = Number(value); return Number.isFinite(parsed) && parsed > lowerBound ? parsed : null; }
function boundedMaximum(value: string, upperBound: number): number | null { const parsed = Number(value); return Number.isFinite(parsed) && parsed < upperBound ? parsed : null; }
function optionalNumberInput(value: number | null | undefined, fallback: number): string { return String(value == null ? fallback : value); }
function profileLocationSummary(profile: Territory) { const locations = profile.locations || []; if (locations.length === 1) return locations[0].label || locations[0].city; if (locations.length > 1) return `${locations.length} cities`; return `${profile.place_label || profile.city} · ${profile.radius_km} km`; }
function batchStateLabel(state?: string) { if (state === "scoring") return "Building"; if (state === "retrying") return "Retrying"; if (state === "ready") return "Ready"; if (state === "partial") return "Partial"; if (state === "empty") return "No matches"; if (state === "failed") return "Needs attention"; return "Set up"; }
function batchStateCopy(batch: ReturnType<typeof useAppData>["profileBatch"]) { if (!batch) return "No lead batch has been generated for this saved search yet."; const progress = batch.location_count && batch.location_count > 1 ? ` ${batch.locations_completed || 0} of ${batch.location_count} cities completed.` : ""; if (["scoring", "retrying"].includes(batch.state)) return `ScoutLead is collecting and evaluating businesses. You can leave this page.${progress}`; if (["ready", "partial"].includes(batch.state)) return `${batch.remaining_count} leads remain for review.${progress}`; if (batch.state === "failed") return `The latest batch could not be completed.${progress}`; return "No indexed businesses matched this search."; }
