export type BusinessExportFormat = "csv" | "json";

export function defaultExportFileName(label: string, suffix = "businesses") {
  const base = slugify(label);
  const normalizedSuffix = slugify(suffix);
  const prefix =
    base === normalizedSuffix || base.endsWith(`-${normalizedSuffix}`) ? base : `${base}-${normalizedSuffix}`;
  return `${prefix}-${new Date().toISOString().slice(0, 10)}`;
}

export function baseExportFileName(value: string) {
  return value.trim().replace(/\.(csv|json)$/i, "").trim();
}

export function normalizeExportFileName(value: string, format: BusinessExportFormat) {
  return `${slugify(baseExportFileName(value))}.${format}`;
}

export function exportContactEmail(value?: string | null) {
  const email = value?.trim() || "";
  if (!email.includes("@")) return "";
  const domain = email.slice(email.lastIndexOf("@") + 1).toLowerCase();
  return /\.(png|jpe?g|gif|webp|svg)$/.test(domain) ? "" : email;
}

export function exportBusinesses(contacts: DiscoveryResult[], fileName: string, format: BusinessExportFormat) {
  const rows = contacts.map((contact) => ({
    business_id: contact.business_id || contact.id,
    company: contact.company_name,
    contact_name: getContactName(contact) || contact.research?.contact_name || "",
    email: exportContactEmail(contact.contact_email || contact.research?.contact_email),
    phone: getPhone(contact),
    website: contact.website_url || contact.research?.website_url || "",
    geography: contact.geography || contact.research?.geography || "",
    address: getAddress(contact) || null,
    google_profile_url: getGoogleProfileUrl(contact) || null,
    google_rating: getRating(contact) ?? null,
    google_review_count: getReviewCount(contact) ?? null,
    source: contact.source,
    saved_search_id: contact.territory_id || null,
    status: contact.review_status === "not_fit" || (contact.contact_policy_status && contact.contact_policy_status !== "allowed")
      ? "dismissed"
      : contact.last_contacted_at ? "contacted" : contact.shortlisted_at ? "shortlisted" : "lead",
  }));
  const contents = format === "json"
    ? JSON.stringify({ business_count: rows.length, businesses: rows }, null, 2)
    : [Object.keys(rows[0]).join(","), ...rows.map((row) => Object.values(row).map(csvCell).join(","))].join("\r\n");
  const mime = format === "json" ? "application/json" : "text/csv";
  const blob = new Blob([contents], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = normalizeExportFileName(fileName, format);
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function slugify(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "contacts";
}

function csvCell(value: string | number | null | undefined) {
  const text = String(value ?? "");
  const safeText = typeof value === "string" && /^[\s]*[=+\-@]|^[\t\r\n]/.test(text) ? `'${text}` : text;
  return `"${safeText.replace(/"/g, '""')}"`;
}
import type { DiscoveryResult } from "../types/domain";
import { getAddress, getContactName, getGoogleProfileUrl, getPhone, getRating, getReviewCount } from "./contact-fields";
