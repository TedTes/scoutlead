export function defaultExportFileName(label: string, suffix = "contacts") {
  const base = slugify(label);
  const normalizedSuffix = slugify(suffix);
  const prefix =
    base === normalizedSuffix || base.endsWith(`-${normalizedSuffix}`) ? base : `${base}-${normalizedSuffix}`;
  return `${prefix}-${new Date().toISOString().slice(0, 10)}`;
}

export function baseExportFileName(value: string) {
  return value.trim().replace(/\.csv$/i, "").trim();
}

export function normalizeExportFileName(value: string) {
  return `${slugify(baseExportFileName(value))}.csv`;
}

export function exportContactEmail(value?: string | null) {
  const email = value?.trim() || "";
  if (!email.includes("@")) return "";
  const domain = email.slice(email.lastIndexOf("@") + 1).toLowerCase();
  return /\.(png|jpe?g|gif|webp|svg)$/.test(domain) ? "" : email;
}

export function exportContactsCsv(contacts: DiscoveryResult[], fileName: string) {
  const rows = contacts.map((contact) => ({
    company: contact.company_name,
    contact_name: getContactName(contact) || contact.research?.contact_name || "",
    email: exportContactEmail(contact.contact_email || contact.research?.contact_email),
    phone: getPhone(contact),
    website: contact.website_url || contact.research?.website_url || "",
    geography: contact.geography || contact.research?.geography || "",
  }));
  const headers = Object.keys(rows[0] || { company: "" });
  const csv = [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => csvCell(row[header as keyof typeof row])).join(",")),
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = normalizeExportFileName(fileName);
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function slugify(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "contacts";
}

function csvCell(value: string | number | undefined) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}
import type { DiscoveryResult } from "../types/domain";
import { getContactName, getPhone } from "./contact-fields";
