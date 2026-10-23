import { ArrowRight, Check, ChevronDown, Copy, LoaderCircle, MapPin, Pencil, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Circle, CircleMarker, MapContainer, TileLayer, useMap } from "react-leaflet";

import { useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type { PlaceOption, ProfileCreateInput, ProfileCustomerKind, ProfileExclusion, ProfileOptions, Territory } from "../types/domain";

const SYSTEM_EXCLUSIONS: ProfileExclusion[] = ["closed", "directories"];
type FormMode = "create" | "edit" | "clone";

export function AudienceProfileScreen() {
  const { createProfile, updateProfile, profileBatch, selectedProduct, selectedProductId, selectedProfile, territoryApi } = useAppData();
  const { showToast } = useToast();
  const [profileOptions, setProfileOptions] = useState<ProfileOptions | null>(null);
  const [optionsError, setOptionsError] = useState(false);
  const [mode, setMode] = useState<FormMode>("create");
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [nicheId, setNicheId] = useState("");
  const [customerKind, setCustomerKind] = useState<ProfileCustomerKind>("residential");
  const [placeQuery, setPlaceQuery] = useState("");
  const [selectedPlace, setSelectedPlace] = useState<PlaceOption | null>(null);
  const [placeOptions, setPlaceOptions] = useState<PlaceOption[]>([]);
  const [placeBusy, setPlaceBusy] = useState(false);
  const [placeOpen, setPlaceOpen] = useState(false);
  const [radiusKm, setRadiusKm] = useState(25);
  const [batchSize, setBatchSize] = useState(25);
  const [refillPolicy, setRefillPolicy] = useState<Territory["refill_policy"]>("when_depleted");
  const [services, setServices] = useState<string[]>([]);
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
  const serviceOptions = profileOptions?.services || [];
  const enabledServiceKeys = new Set(serviceOptions.filter((service) => service.enabled).map((service) => service.key));
  const valid = Boolean(selectedProductId && nicheId && selectedPlace && services.length && services.every((service) => enabledServiceKeys.has(service)));
  const activeBatch = useMemo(() => profileBatch?.audience.id === selectedProfile?.id ? profileBatch : null, [profileBatch, selectedProfile?.id]);

  const beginEdit = (nextMode: "edit" | "clone") => {
    if (!selectedProfile) return;
    setMode(nextMode);
    setEditing(true);
    setName(nextMode === "clone" ? `${selectedProfile.label} copy` : selectedProfile.label);
    setNicheId(selectedProfile.niche_id);
    setCustomerKind(selectedProfile.customer_kind);
    const place = profilePlace(selectedProfile);
    setSelectedPlace(place);
    setPlaceQuery(place?.label || selectedProfile.place_label || selectedProfile.city);
    setRadiusKm(selectedProfile.radius_km);
    setBatchSize(selectedProfile.batch_size);
    setRefillPolicy(selectedProfile.refill_policy);
    setServices(selectedProfile.service_keys);
  };

  if (selectedProfile && !editing) {
    const scoring = activeBatch?.state === "scoring" || activeBatch?.state === "retrying";
    return <section className="audience-status-screen">
      <header className="audience-page-heading audience-status-heading"><div><span>Audience</span><h1>{selectedProfile.label}</h1><p>{selectedProfile.niche_label || "Local businesses"} · {customersServedLabel(selectedProfile.customer_kind)} · {selectedProfile.place_label || selectedProfile.city} · {selectedProfile.radius_km} km</p></div><div className="audience-status-actions"><button className="secondary" type="button" onClick={() => beginEdit("clone")}><Copy size={14} /> Clone</button><button className="secondary" type="button" onClick={() => beginEdit("edit")}><Pencil size={14} /> Edit</button></div></header>
      <div className="audience-status-panel"><span className={`audience-state is-${activeBatch?.state || "setup"}`}>{scoring ? <LoaderCircle className="sl-spin" size={15} /> : <Check size={15} />}{batchStateLabel(activeBatch?.state)}</span><strong>{activeBatch?.result_count || 0} leads in the current batch</strong><p>{batchStateCopy(activeBatch)}</p></div>
    </section>;
  }

  const submit = async () => {
    if (!valid || !selectedPlace || submittingRef.current) return;
    submittingRef.current = true;
    setSaving(true);
    const market = { place_label: selectedPlace.label, place_provider: selectedPlace.provider, place_external_id: selectedPlace.external_id, country_code: selectedPlace.country_code, latitude: selectedPlace.latitude, longitude: selectedPlace.longitude, radius_km: radiusKm };
    try {
      if (mode === "edit" && selectedProfile) {
        await updateProfile(selectedProfile.id, { label: name.trim() || autoName(selectedNiche?.label, selectedPlace, radiusKm, services, serviceOptions), niche_id: nicheId, customer_kind: customerKind, ...market, service_keys: services, batch_size: batchSize, refill_policy: refillPolicy, exclusion_keys: SYSTEM_EXCLUSIONS });
        setEditing(false);
        showToast({ title: "Audience updated", message: "New criteria will apply to the next batch.", tone: "green" });
      } else {
        const input: ProfileCreateInput = { product_id: selectedProductId, name: name.trim() || autoName(selectedNiche?.label, selectedPlace, radiusKm, services, serviceOptions), niche_id: nicheId, customer_kind: customerKind, market, services, signals: [], exclude: SYSTEM_EXCLUSIONS, limit: batchSize, refill_policy: refillPolicy, exclude_already_delivered: true, ...(mode === "clone" && selectedProfile ? { clone_from_id: selectedProfile.id } : {}) };
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
  return <section className="audience-setup-screen">
    <header className="audience-page-heading"><div><span>{selectedProduct?.product_name || "Product"}</span><h1>{mode === "edit" ? "Edit audience" : mode === "clone" ? "Clone audience" : <>Define your <em>next</em> audience</>}</h1><p>Choose who to find, where to search, and the opportunity ScoutLead should verify.</p></div></header>
    <form className="audience-setup-form" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <section className="audience-form-row" aria-labelledby="audience-trade-title"><div className="audience-row-copy"><span className="audience-step">01 · Who</span><h2 id="audience-trade-title">Business type <em>*</em></h2><p>Choose one focused category.</p></div><div className="audience-row-control"><div className="audience-chip-options" role="radiogroup" aria-labelledby="audience-trade-title">{businessTypes.map((businessType) => <button aria-pressed={nicheId === businessType.id} className={nicheId === businessType.id ? "is-selected" : ""} key={businessType.id} type="button" onClick={() => setNicheId(businessType.id)}>{nicheId === businessType.id ? <Check size={13} /> : null}{businessType.label}</button>)}</div>{!profileOptions && !optionsError ? <p className="audience-row-status"><LoaderCircle className="sl-spin" size={14} />Loading business types</p> : null}{optionsError ? <p className="audience-row-error">Business types unavailable.</p> : null}</div></section>
      <section className="audience-form-row" aria-labelledby="audience-kind-title"><div className="audience-row-copy"><h2 id="audience-kind-title">Customers served <em>*</em></h2><p>Which customers these businesses serve.</p></div><div className="audience-row-control"><div className="audience-segmented" role="radiogroup" aria-labelledby="audience-kind-title">{(["residential", "commercial", "both"] as ProfileCustomerKind[]).map((value) => <label key={value}><input type="radio" name="customer-kind" value={value} checked={customerKind === value} onChange={() => setCustomerKind(value)} /><span>{customersServedLabel(value)}</span></label>)}</div></div></section>
      <section className="audience-form-row audience-location-row" aria-labelledby="audience-market-title"><div className="audience-row-copy"><span className="audience-step">02 · Where</span><h2 id="audience-market-title">Search area <em>*</em></h2><p>Select a confirmed place and coverage radius.</p></div><div className="audience-location-control"><label className="audience-field"><span>Place</span><div className={`audience-place-picker${selectedPlace ? " is-confirmed" : ""}`}><MapPin aria-hidden="true" size={15} /><input autoComplete="off" placeholder="Search a city" value={placeQuery} onFocus={() => setPlaceOpen(true)} onChange={(event) => { setPlaceQuery(event.target.value); setSelectedPlace(null); setPlaceOpen(true); }} />{placeBusy ? <LoaderCircle className="sl-spin" size={14} /> : selectedPlace ? <Check size={14} /> : null}{placeQuery ? <button aria-label="Clear place" type="button" onClick={() => { setPlaceQuery(""); setSelectedPlace(null); setPlaceOptions([]); }}><X size={14} /></button> : null}{placeOpen && placeOptions.length ? <div className="audience-place-options" role="listbox">{placeOptions.map((place) => <button key={`${place.provider}:${place.external_id || place.label}`} role="option" type="button" onClick={() => { setSelectedPlace(place); setPlaceQuery(place.label); setPlaceOpen(false); setPlaceOptions([]); }}><MapPin size={14} /><span>{place.label}</span></button>)}</div> : null}</div>{selectedPlace ? <small>Confirmed by {placeProviderLabel(selectedPlace.provider)}</small> : <small>Select a result to confirm the search center.</small>}</label><div className="audience-radius-options" role="radiogroup" aria-label="Coverage radius">{(profileOptions?.radius_presets || [10, 25, 50]).map((value) => <button aria-pressed={radiusKm === value} className={radiusKm === value ? "is-selected" : ""} disabled={!selectedPlace} key={value} type="button" onClick={() => setRadiusKm(value)}>{value} km</button>)}</div>{selectedPlace ? <CoverageMap place={selectedPlace} radiusKm={radiusKm} /> : <div className="audience-map-placeholder"><MapPin size={22} /><span>Select a place to preview coverage.</span></div>}</div></section>
      <section className="audience-form-row" aria-labelledby="audience-signals-title"><div className="audience-row-copy"><span className="audience-step">03 · Opportunity</span><h2 id="audience-signals-title">What opportunity should ScoutLead look for? <em>*</em></h2><p>Only evidence-backed opportunities can be selected.</p></div><div className="audience-row-control"><div className="audience-focus-list" role="group" aria-labelledby="audience-signals-title">{serviceOptions.map((service) => { const selected = services.includes(service.key); const enabled = service.enabled; return <label className={`${selected ? "is-selected" : ""}${enabled ? "" : " is-disabled"}`} key={service.key}><input type="checkbox" checked={selected} disabled={!enabled} onChange={() => setServices(toggleValue(services, service.key))} /><span><strong>{service.label}{!enabled ? <em>{service.signals.length ? "Preparing data" : "Coming soon"}</em> : null}</strong><small>{service.description}</small></span></label>; })}</div></div></section>
      <section className="audience-advanced-section"><button aria-expanded={advancedOpen} className="audience-advanced-toggle" type="button" onClick={() => setAdvancedOpen((open) => !open)}><span><strong>Advanced</strong><small>Delivery size and automatic refill</small></span><ChevronDown className={advancedOpen ? "is-open" : ""} size={17} /></button>{advancedOpen ? <div className="audience-advanced-fields"><label className="audience-field"><span>First batch</span><select className="audience-input" value={batchSize} onChange={(event) => setBatchSize(Number(event.target.value))}>{(profileOptions?.batch_size_presets || [15, 25, 40]).map((value) => <option key={value} value={value}>{value} leads</option>)}</select></label><label className="audience-field"><span>Refill</span><select className="audience-input" value={refillPolicy} onChange={(event) => setRefillPolicy(event.target.value as Territory["refill_policy"])}><option value="when_depleted">When depleted</option><option value="manual">Manual</option><option value="weekly">Weekly</option><option value="biweekly">Every two weeks</option><option value="monthly">Monthly</option></select></label></div> : null}</section>
      <section className="audience-form-row" aria-labelledby="audience-name-title"><div className="audience-row-copy"><h2 id="audience-name-title">Name</h2><p>Optional. A descriptive name is generated automatically.</p></div><div className="audience-row-control"><input aria-label="Audience name" className="audience-input" placeholder={generatedName || "Audience name"} type="text" value={name} onChange={(event) => setName(event.target.value)} /></div></section>
      <div className="audience-form-footer"><p className="audience-form-hint" aria-live="polite">{formHint}</p><div className="audience-form-actions">{editing ? <button className="secondary" type="button" onClick={() => setEditing(false)}>Cancel</button> : null}<button className="runbtn audience-create-button" disabled={!valid || saving} type="submit">{saving ? <LoaderCircle className="sl-spin" size={15} /> : null}<span>{mode === "edit" ? "Save audience" : mode === "clone" ? "Create copy" : "Create audience"}</span>{!saving ? <ArrowRight size={15} /> : null}</button></div></div>
    </form>
  </section>;
}

function CoverageMap({ place, radiusKm }: { place: PlaceOption; radiusKm: number }) {
  const center: [number, number] = [place.latitude, place.longitude];
  return <div className="audience-coverage-map"><MapContainer attributionControl center={center} dragging={false} doubleClickZoom={false} keyboard={false} scrollWheelZoom={false} zoom={9} zoomControl={false}><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" /><MapViewport center={center} radiusKm={radiusKm} /><Circle center={center} pathOptions={{ color: "#6d4aff", fillColor: "#8066ff", fillOpacity: 0.16, weight: 2 }} radius={radiusKm * 1000} /><CircleMarker center={center} pathOptions={{ color: "#ffffff", fillColor: "#5b3df5", fillOpacity: 1, weight: 3 }} radius={7} /></MapContainer><span className="audience-map-caption">Coverage preview · {radiusKm} km from {place.label.split(",")[0]}</span></div>;
}

function MapViewport({ center, radiusKm }: { center: [number, number]; radiusKm: number }) { const map = useMap(); useEffect(() => { const latitudeDelta = Math.max(0.03, radiusKm / 90); const longitudeDelta = Math.max(0.03, radiusKm / (90 * Math.max(0.25, Math.cos(center[0] * Math.PI / 180)))); map.fitBounds([[center[0] - latitudeDelta, center[1] - longitudeDelta], [center[0] + latitudeDelta, center[1] + longitudeDelta]], { animate: false, padding: [12, 12] }); }, [center, map, radiusKm]); return null; }
function profilePlace(profile: Territory): PlaceOption | null { if (profile.latitude == null || profile.longitude == null) return null; return { label: profile.place_label || profile.city, provider: profile.place_provider || "stored", external_id: profile.place_external_id, country_code: profile.country_code, latitude: profile.latitude, longitude: profile.longitude }; }
function autoName(nicheLabel: string | undefined, place: PlaceOption | null, radiusKm: number, services: string[], serviceOptions: ProfileOptions["services"]) { const opportunity = serviceOptions.find((service) => service.key === services[0])?.label; return [nicheLabel && place ? `${nicheLabel} near ${place.label.split(",")[0]}` : nicheLabel, place ? `${radiusKm} km` : null, opportunity].filter(Boolean).join(" · "); }
function toggleValue<T extends string>(values: T[], value: T): T[] { return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]; }
function getFormHint(nicheId: string, place: PlaceOption | null, services: string[]) { if (!nicheId) return "Choose a business type to continue."; if (!place) return "Select and confirm a place to continue."; if (!services.length) return "Choose at least one opportunity to continue."; return "Ready to save this audience."; }
function customersServedLabel(value: ProfileCustomerKind) { return value === "both" ? "Residential and commercial" : value.charAt(0).toUpperCase() + value.slice(1); }
function placeProviderLabel(value: string) { if (value === "google_places") return "Google Places"; if (value === "openstreetmap_nominatim") return "OpenStreetMap"; return "ScoutLead"; }
function batchStateLabel(state?: string) { if (state === "scoring") return "Building"; if (state === "retrying") return "Retrying"; if (state === "ready") return "Ready"; if (state === "partial") return "Partial"; if (state === "empty") return "No matches"; if (state === "failed") return "Needs attention"; return "Set up"; }
function batchStateCopy(batch: ReturnType<typeof useAppData>["profileBatch"]) { if (!batch) return "No lead batch has been generated for this audience yet."; if (["scoring", "retrying"].includes(batch.state)) return "ScoutLead is collecting and evaluating businesses. You can leave this page."; if (["ready", "partial"].includes(batch.state)) return `${batch.remaining_count} leads remain for review.`; if (batch.state === "failed") return "The latest batch could not be completed."; return "No indexed businesses matched this audience."; }
