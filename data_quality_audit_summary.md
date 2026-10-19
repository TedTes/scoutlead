# Current business-data quality audit

Audit date: 2026-10-18

This audit was read-only. It did not update validation results, memberships,
facts, businesses, leads, or source records.

## Scope

- 1,419 business-niche-market memberships
- 1,307 distinct businesses
- 1,419 membership source observations
- Seven populated niches; pest control and garage-door services currently have
  no inventory

## Current-rule evaluation

| Outcome | Memberships | Share |
| --- | ---: | ---: |
| Publishable | 1,250 | 88.1% |
| Needs review | 138 | 9.7% |
| Rejected | 31 | 2.2% |

These are deterministic eligibility results against stored evidence, not human-
verified precision. The existing 30-record human review remains the accuracy
benchmark.

### Validation dimensions

| Dimension | Passed | Uncertain | Failed |
| --- | ---: | ---: | ---: |
| Identity | 1,419 | 0 | 0 |
| Business identity | 1,391 | 0 | 28 |
| Trade | 1,369 | 47 | 3 |
| Location | 1,308 | 111 | 0 |

Most review cases are missing independent location evidence. The audit also
found that secondary Google categories were causing false trade rejection; the
validator now treats only the title and primary category/type as decisive
exclusion evidence.

## Source outcomes

| Source | Publishable | Review | Rejected |
| --- | ---: | ---: | ---: |
| Google Places seed | 973 | 30 | 6 |
| Google Places live | 142 | 76 | 0 |
| Company website seed | 56 | 0 | 0 |
| OpenStreetMap seed | 45 | 0 | 0 |
| OpenStreetMap live | 33 | 21 | 3 |
| Configured web search | 1 | 11 | 3 |
| Kijiji | 0 | 0 | 19 |

Kijiji should not contribute searchable inventory without a confirmed canonical
business identity. Configured web search should remain evidence/fallback input,
not a primary canonical-business source.

## Stored-data findings

- 19 form facts lack sufficient owned-website support.
- No current website-status contradictions were detected.
- Six duplicate-domain groups and one duplicate name/market group require
  review; social-media domains should not be identity keys.
- 798 memberships are legacy/seed rows without a matching business-index
  segment. They can still be served by niche and market, but have weaker refresh
  lineage.
- Only 9 of 1,711 contact rows are marked valid; 1,638 remain unverified.

## Reports

- `data_quality_audit_current.json`: aggregate current-rule membership results
- `data_quality_audit_details_current.json`: per-membership evidence and reasons
- `business_pool_audit_current.json`: canonical, contact, duplicate, fact, source,
  and lifecycle metrics
- `data_quality_evaluation_30.md`: existing human-reviewed accuracy benchmark

## Safe next actions

1. Review the 31 rejected and 138 uncertain memberships in the admin workflow.
2. Reconcile the 19 unsupported form facts.
3. Add explicit index segments or lineage metadata for legacy seed memberships.
4. Expand human-reviewed samples by niche and source before applying bulk repair.
5. Apply validation results only in canary batches after review.
