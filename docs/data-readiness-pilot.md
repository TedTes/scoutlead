# Data readiness pilot

Generated from the configured development database on 2026-10-29/30. The pilot was
read-only: it did not mutate the database or call an external provider.

## Decision

Do not bulk-seed 1,000 businesses per city yet. First improve the precision of the
existing validation and deduplication path. After that, populate uncovered markets
on demand in small, budgeted batches.

The database has enough Toronto data to exercise the product, but the amount of
data is currently larger than the amount that can be published confidently.
Vancouver needs collection, not a larger global seed.

## Current inventory

The business-pool audit found:

| Measure | Count |
| --- | ---: |
| Businesses | 1,699 |
| Publishable | 636 |
| Needs review | 883 |
| Unvalidated | 120 |
| Rejected | 60 |
| With website | 1,336 |
| With phone | 1,363 |
| With address | 1,467 |
| With embedding | 862 |

Only 8 businesses have an email classified as valid. Most contact email records are
unverified, so email presence must not be presented as verified deliverability.

## City and category coverage

The table below applies the current eligibility rules, coordinates, and a 25 km
radius. The target is 100 validated businesses per category.

| Market | Category | In radius | Validated | Uncertain | Rejected | Missing coordinates | Deficit |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Toronto | Landscaping | 67 | 41 | 23 | 3 | 46 | 59 |
| Toronto | Painting | 405* | 157 | 240 | 3 | 345 | 0 |
| Toronto | HVAC | 142 | 87 | 52 | 3 | 28 | 13 |
| Vancouver | Landscaping | 0 | 0 | 0 | 0 | 46 | 100 |
| Vancouver | Painting | 2 | 0 | 2 | 0 | 345 | 100 |
| Vancouver | HVAC | 0 | 0 | 0 | 0 | 28 | 100 |

\* The export inspected the first 400 candidates and records that the candidate
limit was reached.

## Reliability findings

### Identity and category precision

Manual inspection of the validated sample still found ambiguous records and
duplicate canonical businesses. Examples include repeated businesses sharing a
domain or phone and records whose name/domain do not clearly represent the target
trade. A passed historical trade validation is therefore not yet sufficient proof
that the business is a correct lead.

Generic search-result titles and directory/list pages also remain in the business
pool. They should be quarantined and cleaned only after a reviewed dry-run report.

### Observation integrity

The source-observation audit inspected 15,593 observations:

- 15,205 passed the stored-payload integrity check.
- 388 have a content-hash mismatch.
- 159 duplicate-content groups were found.
- 9 external identifiers are attached to more than one business.

The hash mismatches are concentrated in `company_website_seed`, `google_places`,
`website_presence_check`, and `openstreetmap`. Current repository writes take a
deep-copy snapshot and hash that snapshot, so the mismatches may be legacy records
or later payload replacements. Do not bulk-rehash them: that would erase the signal
that stored evidence changed. Recollect or explicitly review the affected evidence.

### Fact reliability

The fact audit inspected 18,097 facts and classified 3,955 as healthy under the
current checks. The same fact may have more than one issue:

| Issue | Count |
| --- | ---: |
| Missing current validation | 14,125 |
| Expired or unbounded | 3,046 |
| Source-contract mismatch | 2,861 |
| Resolved fact/claim mismatch | 1,374 |
| Unknown value | 526 |
| Missing claim | 173 |
| Missing source observation | 94 |

These facts should remain staged and excluded from matching until they are
revalidated. They should not be deleted because they retain provenance and can be
reconciled from new evidence.

## Quality gates before scaling

A category/market should be considered ready only when a human-reviewed benchmark
sample meets all of these gates:

1. At least 95% of sampled businesses genuinely belong to the requested category.
2. No more than 2% unresolved duplicate businesses in the sample.
3. No more than 2% incorrect missing-website or missing-feature conclusions.
4. Every publishable fact has a current validation, claim, and source observation.
5. At least 90% of candidate businesses have usable coordinates.
6. Unknown or unreachable evidence never becomes a verified gap.
7. Directory pages, listicles, marketplaces, generic service pages, and search
   result pages never create a canonical business without independent identity
   evidence.

## Recommended sequence

1. Review `review-sample.json` and label category correctness, duplicate identity,
   and website-status correctness. This establishes measured precision.
2. Repair category validation so it requires independent business evidence rather
   than treating query return as category proof.
3. Merge duplicate businesses using provider ID, domain, phone, and location.
4. Recollect the 388 observations with hash mismatches and revalidate the 94 facts
   missing source observations.
5. Backfill coordinates for otherwise eligible Toronto records before collecting
   more Toronto businesses.
6. Run a reviewed Vancouver pilot of at most 100 candidates per category. Use hard
   provider request budgets and stop when the quality benchmark fails.
7. Add scheduled refresh only for markets with active audiences. Pre-seed a market
   only after usage proves recurring demand.

## Read-only export

```bash
python scripts/prepare_city_category_data.py \
  --target-count 100 \
  --provider-budget google_places=10 \
  --provider-budget openstreetmap=1 \
  --output-dir data/readiness/current
```
The provider budgets are recorded as a proposed hard cap. The command never calls
those providers. It writes validated, uncertain, rejected, manifest, summary, and
review-sample JSON files. The generated data is intentionally gitignored.

To inspect another market without writing to the database:

```bash
python scripts/prepare_city_category_data.py \
  --market "Calgary=51.0447,-114.0719" \
  --category home_service_hvac \
  --radius-km 25 \
  --target-count 100 \
  --output-dir data/readiness/calgary-hvac
```
