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

export function slugify(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "contacts";
}
