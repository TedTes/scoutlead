import {
  discoveryNiches,
  discoveryTemplates,
  type DiscoveryNiche,
  type DiscoveryTemplate,
} from "../data/discovery-templates";
import type { Product } from "../types/domain";

const DEFAULT_TEMPLATE_ORDER = [
  "local_service_shops",
  "recent_service_listings",
  "quote_ready_businesses",
  "owner_operated_providers",
  "estimate_form_businesses",
  "high_review_local_shops",
  "emergency_service_operators",
  "b2b_service_providers",
];

export type TemplateContext = {
  service: string;
  city: string;
  region: string;
  business_type: string;
  nicheIds: string[];
};

export type ResolvedDiscoveryTemplate = DiscoveryTemplate & {
  query: string;
  label: string;
  tag: string;
};

export function searchDiscoveryTemplates({
  product,
  query,
  limit = 8,
}: {
  product?: Product;
  query?: string;
  limit?: number;
}): ResolvedDiscoveryTemplate[] {
  const context = inferTemplateContext(product);
  const searchTokens = tokenize(query || "");
  return discoveryTemplates
    .map((template) => ({
      template,
      score: templateScore(template, context, searchTokens),
    }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return defaultTemplateRank(a.template.id) - defaultTemplateRank(b.template.id);
    })
    .slice(0, limit)
    .map(({ template }) => resolveDiscoveryTemplate(template, context));
}

export function inferTemplateContext(product: Product | undefined): TemplateContext {
  const productText = [
    product?.product_name,
    product?.product_description,
    product?.target_customer,
    product?.target_geography,
    product?.problem_being_solved,
    product?.value_proposition,
  ]
    .filter(Boolean)
    .join(" ");
  const nicheIds = matchingNicheIds(productText);
  const primaryNiche = nicheIds.length ? nicheById(nicheIds[0]) : undefined;
  const region = product?.target_geography?.trim() || "";
  return {
    service: primaryNiche?.defaultService || inferService(productText),
    city: firstKnownCity(region || product?.product_description || productText) || "Toronto",
    region,
    business_type: primaryNiche?.defaultBusinessType || inferBusinessType(productText),
    nicheIds,
  };
}

export function resolveDiscoveryTemplate(
  template: DiscoveryTemplate,
  context: TemplateContext,
): ResolvedDiscoveryTemplate {
  const query = template.promptTemplate.replace(/\{\{([a-z_]+)\}\}/g, (_, key: string) => {
    const value = context[key as keyof TemplateContext];
    return typeof value === "string" && value.trim() ? value : key.replace(/_/g, " ");
  });
  return {
    ...template,
    query,
    label: template.title,
    tag: template.tags[0] || template.intent.replace(/_/g, " "),
  };
}

function templateScore(template: DiscoveryTemplate, context: TemplateContext, searchTokens: string[]) {
  let score = 1;
  const nicheMatches = template.nicheIds.filter((id) => context.nicheIds.includes(id)).length;
  score += nicheMatches * 8;
  score += template.requiredVars.every((variable) => Boolean(context[variable])) ? 2 : -2;
  if (!searchTokens.length) return score;

  const haystack = tokenize(
    [
      template.title,
      template.shortDescription,
      template.intent,
      template.tags.join(" "),
      template.searchTerms.join(" "),
      template.promptTemplate,
      ...template.nicheIds.map((id) => nicheById(id)?.aliases.join(" ") || ""),
    ].join(" "),
  );
  const matched = searchTokens.filter((token) => haystack.some((item) => item.includes(token)));
  if (!matched.length) return 0;
  return score + matched.length * 6;
}

function matchingNicheIds(text: string) {
  const normalized = text.toLowerCase();
  return discoveryNiches
    .filter((niche) => niche.aliases.some((alias) => normalized.includes(alias.toLowerCase())))
    .map((niche) => niche.id);
}

function nicheById(id: string): DiscoveryNiche | undefined {
  return discoveryNiches.find((niche) => niche.id === id);
}

function inferService(text: string) {
  const lower = text.toLowerCase();
  if (lower.includes("hvac")) return "HVAC";
  if (lower.includes("auto")) return "auto service";
  if (lower.includes("paint")) return "painting";
  return "local service";
}

function inferBusinessType(text: string) {
  const lower = text.toLowerCase();
  if (lower.includes("hvac")) return "HVAC businesses";
  if (lower.includes("auto")) return "auto service businesses";
  if (lower.includes("paint")) return "painting businesses";
  return "service businesses";
}

function firstKnownCity(value: string) {
  const match = value.match(
    /\b(Toronto|Vancouver|Calgary|Montreal|Ottawa|Austin|Dallas|New York|Chicago|Los Angeles)\b/i,
  );
  return match ? titleCase(match[1]) : "";
}

function titleCase(value: string) {
  return value.replace(/\w\S*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase());
}

function tokenize(value: string) {
  return value
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .map((token) => token.trim())
    .filter(Boolean);
}

function defaultTemplateRank(id: string) {
  const index = DEFAULT_TEMPLATE_ORDER.indexOf(id);
  return index === -1 ? Number.MAX_SAFE_INTEGER : index;
}
