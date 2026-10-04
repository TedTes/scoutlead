import { X } from "lucide-react";
import type { SearchIntent } from "../types/domain";

export function SearchIntentChips({
  intent,
  onChange,
}: {
  intent: SearchIntent;
  onChange?: (intent: SearchIntent) => void;
}) {
  const removeCriterion = (id: string) => {
    onChange?.({ ...intent, criteria: intent.criteria.filter((item) => item.id !== id) });
  };
  const removeContact = (requirement: string) => {
    onChange?.({
      ...intent,
      contact_requirements: intent.contact_requirements.filter((item) => item !== requirement),
    });
  };

  return (
    <div className="search-intent-strip" aria-label="Interpreted search criteria">
      <span className="search-intent-chip is-scope">{intent.business_category}</span>
      <span className="search-intent-chip is-scope">{intent.location}</span>
      {intent.criteria.map((criterion) => (
        <span className={`search-intent-chip is-${criterion.mode}`} key={criterion.id}>
          {criterion.description}
          {onChange && !criterion.id.startsWith("product_") ? (
            <button
              aria-label={`Remove ${criterion.description}`}
              onClick={() => removeCriterion(criterion.id)}
              title={`Remove ${criterion.description}`}
              type="button"
            >
              <X size={12} />
            </button>
          ) : criterion.id.startsWith("product_") ? (
            <small>Product default</small>
          ) : null}
        </span>
      ))}
      {intent.contact_requirements.map((requirement) => (
        <span className="search-intent-chip is-contact" key={requirement}>
          Contact: {requirement.replace("_", " ")}
          {onChange ? (
            <button
              aria-label={`Remove contact requirement ${requirement}`}
              onClick={() => removeContact(requirement)}
              title={`Remove contact requirement ${requirement}`}
              type="button"
            >
              <X size={12} />
            </button>
          ) : null}
        </span>
      ))}
    </div>
  );
}

export function searchIntentFromRun(
  run: { source_inputs?: Record<string, unknown> } | undefined,
): SearchIntent | null {
  const value = run?.source_inputs?.search_intent;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Partial<SearchIntent>;
  if (!candidate.business_category || !candidate.location || !Array.isArray(candidate.criteria)) {
    return null;
  }
  return {
    schema_version: candidate.schema_version || 1,
    business_category: candidate.business_category,
    location: candidate.location,
    country: candidate.country || "",
    included_subcategories: candidate.included_subcategories || [],
    criteria: candidate.criteria,
    contact_requirements: candidate.contact_requirements || [],
    required_signals: candidate.required_signals || [],
    excluded_result_types: candidate.excluded_result_types || [],
    search_query: candidate.search_query || `${candidate.business_category} in ${candidate.location}`,
    search_url: candidate.search_url || "",
    confidence: candidate.confidence || 0,
    rationale: candidate.rationale || "Saved search interpretation",
  };
}
