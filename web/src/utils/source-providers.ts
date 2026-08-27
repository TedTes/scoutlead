import type { SourceProvider, SourceRequestSource } from "../types/domain";

export const sourceCatalog: SourceProvider[] = [
  { id: "google_places", label: "Google Places", configured: false, detail: "Local business discovery" },
  { id: "apify_actor", label: "Kijiji", configured: false, detail: "Classified service listings" },
  { id: "directories", label: "Directories", configured: false, detail: "Trade associations" },
  { id: "website_list", label: "Website lookup", configured: false, detail: "Known web presence" },
];

export function mergeSourceProviders(providers: SourceProvider[]) {
  const byId = new Map<string, SourceProvider>();
  for (const provider of sourceCatalog) byId.set(provider.id, provider);

  for (const provider of providers) {
    const catalogProvider = byId.get(provider.id);
    const label =
      provider.label && !isInternalProviderLabel(provider.label)
        ? provider.label
        : catalogProvider?.label || provider.id;
    byId.set(provider.id, {
      ...catalogProvider,
      ...provider,
      label,
      detail: displayProviderDetail(provider.detail, catalogProvider?.detail),
    });
  }

  return Array.from(byId.values());
}

function isInternalProviderLabel(label: string) {
  return ["apify actor", "configured apify actor", "marketplace scraper"].includes(label.trim().toLowerCase());
}

function displayProviderDetail(detail: string | null | undefined, fallback: string | null | undefined) {
  if (!detail || /apify actor/i.test(detail)) return fallback || null;
  return detail;
}

export function configuredSourceProviders(providers: SourceProvider[]) {
  return mergeSourceProviders(providers).filter((provider) => provider.configured);
}

export function normalizeActiveSourceIds(
  sourceIds: SourceRequestSource[],
  providers: SourceProvider[],
): SourceRequestSource[] {
  const configured = configuredSourceProviders(providers);
  const configuredIds = new Set(configured.map((provider) => provider.id));
  const normalized = sourceIds.filter((sourceId, index) => configuredIds.has(sourceId) && sourceIds.indexOf(sourceId) === index);
  if (normalized.length) return normalized;
  return configured[0] ? [configured[0].id] : [];
}
