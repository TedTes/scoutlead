export type DiscoveryTemplateIntent =
  | "local_business"
  | "quote_ready"
  | "estimate_form"
  | "owner_operated"
  | "marketplace_listing"
  | "high_review"
  | "emergency_service"
  | "b2b_service";

export type DiscoveryTemplateVariable = "service" | "city" | "region" | "business_type";

export type DiscoveryNiche = {
  id: string;
  label: string;
  aliases: string[];
  defaultService: string;
  defaultBusinessType: string;
  defaultSignals: string[];
};

export type DiscoveryTemplate = {
  id: string;
  title: string;
  shortDescription: string;
  nicheIds: string[];
  searchTerms: string[];
  intent: DiscoveryTemplateIntent;
  promptTemplate: string;
  requiredVars: DiscoveryTemplateVariable[];
  tags: string[];
  hiddenSourceStrategy: {
    preferredSources: string[];
    fallbackSources: string[];
  };
};

export const discoveryNiches: DiscoveryNiche[] = [
  {
    id: "painting",
    label: "Painting",
    aliases: ["paint", "painter", "painters", "painting", "painting contractor", "residential painters"],
    defaultService: "painting",
    defaultBusinessType: "painting businesses",
    defaultSignals: ["quote form", "reviews", "phone", "owner contact"],
  },
  {
    id: "hvac",
    label: "HVAC",
    aliases: ["hvac", "heating", "cooling", "heat pump", "boiler", "furnace", "air conditioning"],
    defaultService: "HVAC",
    defaultBusinessType: "HVAC businesses",
    defaultSignals: ["quote form", "reviews", "phone", "service area"],
  },
  {
    id: "auto_services",
    label: "Auto Services",
    aliases: ["auto", "detailing", "car wash", "mechanic", "auto repair", "vehicle service"],
    defaultService: "auto service",
    defaultBusinessType: "auto service businesses",
    defaultSignals: ["phone", "booking page", "reviews", "service descriptions"],
  },
  {
    id: "home_services",
    label: "Home Services",
    aliases: ["contractor", "home service", "renovation", "plumbing", "roofing", "landscaping"],
    defaultService: "home service",
    defaultBusinessType: "home service businesses",
    defaultSignals: ["quote form", "reviews", "phone", "local service area"],
  },
];

export const discoveryTemplates: DiscoveryTemplate[] = [
  {
    id: "local_service_shops",
    title: "Local service shops",
    shortDescription: "Independent local businesses with websites, reviews, and reachable contacts.",
    nicheIds: ["painting", "hvac", "auto_services", "home_services"],
    searchTerms: ["local", "service", "shops", "independent", "website", "reviews", "contact"],
    intent: "local_business",
    promptTemplate:
      "independent {{service}} businesses in {{city}} with a website, strong reviews, and owner contact details",
    requiredVars: ["service", "city"],
    tags: ["Local"],
    hiddenSourceStrategy: {
      preferredSources: ["local_business_index", "public_business_pages"],
      fallbackSources: ["public_listings"],
    },
  },
  {
    id: "quote_ready_businesses",
    title: "Quote-ready businesses",
    shortDescription: "Businesses with quote forms, public contact details, and direct customer proof.",
    nicheIds: ["painting", "hvac", "auto_services", "home_services"],
    searchTerms: ["quote", "estimate", "form", "public contact", "direct customers"],
    intent: "quote_ready",
    promptTemplate:
      "{{business_type}} in {{city}} with quote forms, public contact details, and proof they serve customers directly",
    requiredVars: ["business_type", "city"],
    tags: ["Forms"],
    hiddenSourceStrategy: {
      preferredSources: ["local_business_index", "public_business_pages"],
      fallbackSources: ["public_listings"],
    },
  },
  {
    id: "estimate_form_businesses",
    title: "Estimate-form businesses",
    shortDescription: "Service companies that already collect estimate requests through public pages.",
    nicheIds: ["painting", "hvac", "home_services"],
    searchTerms: ["estimate", "request estimate", "free estimate", "phone", "reviews"],
    intent: "estimate_form",
    promptTemplate:
      "{{service}} businesses in {{city}} with request estimate forms, public phone numbers, and recent customer reviews",
    requiredVars: ["service", "city"],
    tags: ["Forms"],
    hiddenSourceStrategy: {
      preferredSources: ["public_business_pages", "local_business_index"],
      fallbackSources: ["public_listings"],
    },
  },
  {
    id: "owner_operated_providers",
    title: "Owner-operated providers",
    shortDescription: "Small providers where the owner or operator is likely reachable.",
    nicheIds: ["painting", "hvac", "auto_services", "home_services"],
    searchTerms: ["owner", "owner operated", "small", "independent", "solo", "operator"],
    intent: "owner_operated",
    promptTemplate:
      "small owner-operated {{service}} providers in {{city}} with reachable contact details and active service pages",
    requiredVars: ["service", "city"],
    tags: ["Owner"],
    hiddenSourceStrategy: {
      preferredSources: ["public_business_pages", "local_business_index"],
      fallbackSources: ["public_listings"],
    },
  },
  {
    id: "recent_service_listings",
    title: "Recent listings",
    shortDescription: "Recently active service listings with direct phone numbers and clear offers.",
    nicheIds: ["painting", "hvac", "auto_services", "home_services"],
    searchTerms: ["recent", "listing", "marketplace", "phone", "service description", "classified"],
    intent: "marketplace_listing",
    promptTemplate:
      "{{service}} providers in {{city}} with direct phone numbers, recent listings, and clear service descriptions",
    requiredVars: ["service", "city"],
    tags: ["Listings"],
    hiddenSourceStrategy: {
      preferredSources: ["public_listings"],
      fallbackSources: ["local_business_index", "public_business_pages"],
    },
  },
  {
    id: "high_review_local_shops",
    title: "High-review local shops",
    shortDescription: "Local companies with strong reputation signals and direct customer contact options.",
    nicheIds: ["painting", "hvac", "auto_services", "home_services"],
    searchTerms: ["reviews", "rating", "reputation", "website", "contact", "local"],
    intent: "high_review",
    promptTemplate:
      "{{service}} companies in {{city}} with strong reviews, a working website, and direct customer contact options",
    requiredVars: ["service", "city"],
    tags: ["Reviews"],
    hiddenSourceStrategy: {
      preferredSources: ["local_business_index", "public_business_pages"],
      fallbackSources: ["public_listings"],
    },
  },
  {
    id: "emergency_service_operators",
    title: "Emergency service operators",
    shortDescription: "Providers with urgent service pages, direct phone numbers, and clear local coverage.",
    nicheIds: ["hvac", "home_services"],
    searchTerms: ["emergency", "urgent", "same day", "24 hour", "phone", "service area"],
    intent: "emergency_service",
    promptTemplate:
      "{{service}} operators in {{city}} with emergency service pages, direct phone numbers, and clear service areas",
    requiredVars: ["service", "city"],
    tags: ["Urgent"],
    hiddenSourceStrategy: {
      preferredSources: ["public_business_pages", "local_business_index"],
      fallbackSources: ["public_listings"],
    },
  },
  {
    id: "b2b_service_providers",
    title: "B2B service providers",
    shortDescription: "Service companies that sell to other businesses and expose reachable contacts.",
    nicheIds: ["auto_services", "home_services"],
    searchTerms: ["b2b", "commercial", "business", "provider", "contact", "service page"],
    intent: "b2b_service",
    promptTemplate:
      "commercial {{service}} providers in {{city}} with business service pages, reachable contacts, and clear customer proof",
    requiredVars: ["service", "city"],
    tags: ["B2B"],
    hiddenSourceStrategy: {
      preferredSources: ["public_business_pages", "local_business_index"],
      fallbackSources: ["public_listings"],
    },
  },
];
