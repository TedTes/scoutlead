import type { DiscoveryResult } from "../types/domain";

export function getAddress(contact: DiscoveryResult) {
  return getRawString(contact, [
    "formattedAddress",
    "formatted_address",
    "address",
    "streetAddress",
    "fullAddress",
    "location.address",
    "location.name",
    "data.location",
  ]);
}

export function getRating(contact: DiscoveryResult) {
  if (typeof contact.google_rating === "number" && Number.isFinite(contact.google_rating)) {
    return contact.google_rating.toFixed(1);
  }
  const value = getRawNumber(contact, [
    "business_facts.google_rating",
    "rating",
    "averageRating",
    "stars",
    "reviewRating",
    "stats.rating",
  ]);
  return value ? value.toFixed(1) : "";
}

export function getReviewCount(contact: DiscoveryResult) {
  if (
    typeof contact.google_review_count === "number"
    && Number.isFinite(contact.google_review_count)
  ) {
    return String(contact.google_review_count);
  }
  const value = getRawNumber(contact, [
    "business_facts.google_review_count",
    "userRatingCount",
    "user_ratings_total",
    "reviewCount",
    "reviewsCount",
    "reviews",
    "stats.reviews",
  ]);
  return value ? String(value) : "";
}

export function getPhone(contact: DiscoveryResult) {
  if (contact.contact_phone?.trim()) return contact.contact_phone.trim();
  return getRawString(contact, [
    "website_presence.phone",
    "normalized_contact_phone",
    "contact_phone",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "phone",
    "phoneNumber",
    "phone_number",
    "telephone",
    "contactPhone",
    "sellerPhone",
    "ownerPhone",
    "seller.phone",
    "contact.phone",
    "data.phone",
  ]);
}

export function getContactUrl(contact: DiscoveryResult) {
  return getRawString(contact, [
    "contact_url",
    "contactUrl",
    "contactPageUrl",
    "contact_page_url",
    "quote_url",
    "quoteUrl",
    "booking_url",
    "bookingUrl",
    "website_enrichment.contact_url",
    "messagingUrl",
    "messaging_url",
    "seller.messagingUrl",
    "seller.profileUrl",
    "seller.profile_url",
    "profileUrl",
    "profile_url",
  ]);
}

export function getContactName(contact: DiscoveryResult) {
  return getRawString(contact, [
    "normalized_contact_name",
    "contact_name",
    "contactName",
    "sellerName",
    "ownerName",
    "seller.name",
    "contact.name",
    "data.sellerName",
  ]);
}

export function getGoogleProfileUrl(contact: DiscoveryResult) {
  const directUrl = getRawString(contact, [
    "googleMapsUri",
    "google_maps_uri",
    "googleMapsUrl",
    "google_maps_url",
    "mapsUri",
    "maps_url",
  ]);
  if (isGoogleMapsUrl(directUrl)) return directUrl;

  const placeId = getRawString(contact, [
    "google_place_id",
    "googlePlaceId",
    "place_id",
    "placeId",
  ]);
  const query = [contact.company_name, getAddress(contact) || contact.geography]
    .filter(Boolean)
    .join(" ")
    .trim();
  if (!query) return "";

  const params = new URLSearchParams({ api: "1", query });
  if (placeId) params.set("query_place_id", placeId);
  return `https://www.google.com/maps/search/?${params.toString()}`;
}

function isGoogleMapsUrl(value: string) {
  if (!value) return false;
  try {
    const hostname = new URL(value).hostname.toLowerCase();
    return hostname === "maps.google.com"
      || hostname.endsWith(".google.com")
      || hostname === "maps.app.goo.gl"
      || hostname === "goo.gl";
  } catch {
    return false;
  }
}

function getRawString(contact: DiscoveryResult, keys: string[]) {
  for (const raw of getRawObjects(contact)) {
    for (const key of keys) {
      const text = rawValueToString(getRawValue(raw, key));
      if (text) return text;
    }
  }
  return "";
}

function getRawNumber(contact: DiscoveryResult, keys: string[]) {
  for (const raw of getRawObjects(contact)) {
    for (const key of keys) {
      const value = getRawValue(raw, key);
      if (typeof value === "number" && Number.isFinite(value)) return value;
      if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
        return Number(value);
      }
    }
  }
  return 0;
}

export function getRawObjects(contact: DiscoveryResult) {
  const values: Record<string, unknown>[] = [];
  for (const source of contact.raw_sources || []) {
    values.push(source);
    if (isRecord(source.raw)) {
      values.push(source.raw);
      if (isRecord(source.raw.raw)) values.push(source.raw.raw);
    }
  }
  return values;
}

export function getRawValue(raw: Record<string, unknown>, key: string): unknown {
  if (key in raw) return raw[key];
  return key.split(".").reduce<unknown>((value, part) => {
    if (Array.isArray(value)) {
      const index = Number(part);
      return Number.isInteger(index) ? value[index] : undefined;
    }
    if (!isRecord(value)) return undefined;
    return value[part];
  }, raw);
}

export function rawValueToString(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (isRecord(value)) {
    return rawValueToString(
      value.text ?? value.name ?? value.value ?? value.formatted ?? value.display ?? value.label,
    );
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const text = rawValueToString(item);
      if (text) return text;
    }
  }
  return "";
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
