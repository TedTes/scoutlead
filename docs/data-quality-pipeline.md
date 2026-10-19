# Business data quality pipeline

ScoutLead keeps source observations separate from publishable conclusions. New
source items follow this path:

```text
source fetch -> canonical identity -> business validation -> opportunity audit
             -> fact reconciliation -> searchable inventory
```

The required business validations are identity, business identity, trade, and
location. A failed dimension rejects the source item. Missing or uncertain
evidence sends it to review. Only a complete high-confidence result is newly
published. Existing unvalidated inventory remains readable during the migration,
but is excluded as soon as a current validation decision is non-publishable.

Website-derived form facts require trusted website ownership evidence. A source
omitting a website is not proof that the business has no website, and failed
inspection produces an unknown result instead of an absence claim.

## Supported niches

- Painting
- HVAC
- Roofing
- Plumbing
- Electrical
- Residential cleaning
- Landscaping
- Pest control
- Garage-door services

Taxonomy and validation vocabulary live in `agent/niches/catalog.py`. Provider
metadata and versioned niche query templates live in
`agent/source_providers/catalog.py`; runtime enablement and external overrides
are merged by `agent/source_providers/registry.py`. Seed collection, live
discovery, provider listing, and source-plan compilation all consume that
registry. Credentials remain environment-only.

The registry is storage-agnostic: a future database repository can supply the
same provider and template records without changing source compilers or adapters.

## Existing inventory

Run a read-only audit first:

```bash
PYTHONPATH=agent python scripts/audit_business_pool.py --json
PYTHONPATH=agent python scripts/repair_business_quality.py --limit 500 --details
```

To retain complete aggregate reports without changing data:

```bash
PYTHONPATH=agent python scripts/audit_business_pool.py \
  --output business_pool_audit_current.json
PYTHONPATH=agent python scripts/repair_business_quality.py --limit 2000 \
  --output data_quality_audit_current.json
```

Apply validation and fact reconciliation only after reviewing the report:

```bash
PYTHONPATH=agent python scripts/repair_business_quality.py --limit 500 --apply
```

Use `--niche` and `--market` for a canary batch. The repair command does not
delete businesses or alter lead outreach history. It records validation results,
updates source-item workflow state, and rebuilds derived facts.

Older observations without source items can be restored read-only first:

```bash
PYTHONPATH=agent python scripts/restore_legacy_source_items.py
```

`--apply --enqueue` writes the restored source items and queues the normal
validation-and-audit stage.

## Release gate

Generate and review a stratified benchmark before enabling a new niche or market.
The benchmark command includes every catalog niche by default:

```bash
PYTHONPATH=agent python scripts/business_benchmark.py sample \
  --output data/benchmarks/business-accuracy-v1.local.jsonl \
  --market toronto --per-niche 50
```

Do not bulk-import or deploy a niche that fails the benchmark precision and
coverage gate.
