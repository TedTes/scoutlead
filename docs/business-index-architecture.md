# Business index architecture

## Domain boundaries

ScoutLead has three independent domains:

1. **Business Index** continuously collects, validates, resolves, and publishes business data.
2. **Audiences** query only the published portion of the Business Index.
3. **Outreach** starts only after a user acts on an audience result.

Audience execution must not create canonical businesses, resolve identities, inspect websites, or
mutate business facts. An audience may request additional index coverage, but unvalidated records
remain staged until the Business Index publishes them.

## Invariants

- Source observations and fact claims are immutable evidence.
- A canonical fact is a versioned resolution of one or more claims, not the original evidence.
- Unknown information is never converted into negative evidence to improve result counts.
- Identity, trade, location, and requested opportunity facts must pass publication policy before a
  business is eligible for an audience.
- Every published result retains the evidence, validator versions, and publication policy version
  that qualified it.
- Audience runs are deterministic for a fixed index snapshot, policy version, and audience criteria.
- Outreach state cannot affect whether a business is valid index data.

## States

Business publication states:

- `staged`: processing is incomplete or has not yet passed policy.
- `published`: eligible for audience matching under the recorded policy version.
- `quarantined`: invalid, conflicting, or from a quality slice below threshold.
- `stale`: previously publishable evidence is no longer current.

Resolved fact states:

- `confirmed`: direct or sufficiently corroborated evidence.
- `probable`: useful evidence that is below the confirmed threshold.
- `unknown`: no defensible conclusion.
- `conflicted`: credible claims disagree.
- `stale`: the resolving evidence has expired.

Audience run states:

- `queued`, `matching`, `expanding`, `waiting_validation`, `ready`, `partial`, `failed`.

## Asynchronous flow

```text
collect -> immutable observation -> candidate screening -> identity resolution
        -> business validation -> fact claims -> fact resolution
        -> publication policy -> published index

audience criteria -> published-index query -> dedupe/rank -> audience results

sample -> review labels -> quality metrics -> publication policy -> revalidation
```

## Migration baseline

Captured on 2026-10-08 before the publication architecture migration:

- Alembic revision: `20261007_0035`
- Canonical businesses: `1,239`
- Resolved business facts: `5,949`
- Source observations: `3,262`
- Fact changes: `0`
- Existing local benchmark sample: 250 businesses, 50 for each of painting, HVAC, roofing,
  plumbing, and electrical.

The existing records are migration inputs, not automatically trusted published records. They must
be reprocessed through the new validation and publication policy.

## Safe rollout

Run these commands against a staging database first. The benchmark import and index reprocessor are
read-only unless `--apply` is explicitly supplied.

1. Apply schema migrations:

   ```bash
   python -m alembic upgrade head
   ```

2. Export a stratified benchmark sample:

   ```bash
   python scripts/business_benchmark.py sample \
     --market toronto \
     --per-niche 50 \
     --output data/benchmarks/toronto-business-accuracy-v1.jsonl
   ```

3. Review the JSONL records and fill `labels`, `reviewer`, `reviewed_at`, and supporting source URLs.
   Keep `unknown` when the evidence does not support a conclusion.

4. Evaluate the reviewed benchmark before it can affect production policy:

   ```bash
   python scripts/business_benchmark.py evaluate \
     --input data/benchmarks/toronto-business-accuracy-v1.jsonl \
     --minimum-reviewed 200 \
     --require-market toronto
   ```

5. Preview and then import the reviewed labels:

   ```bash
   python scripts/business_benchmark.py import \
     --input data/benchmarks/toronto-business-accuracy-v1.jsonl

   python scripts/business_benchmark.py import \
     --input data/benchmarks/toronto-business-accuracy-v1.jsonl \
     --apply
   ```

6. Preview the reprocessing scope, then run a small canary:

   ```bash
   python scripts/reprocess_business_index.py --market toronto

   python scripts/reprocess_business_index.py \
     --market toronto \
     --niche home_service_painting \
     --limit 25 \
     --apply
   ```

7. Inspect `GET /quality/overview`. Expand the reprocessing scope only when validation,
   publication, stale-evidence, dead-letter, and benchmark metrics are understood.

8. Reprocess the remaining measured scopes:

   ```bash
   python scripts/reprocess_business_index.py --market toronto --apply
   ```

An audience can return fewer than its requested count while coverage is being collected or quality
is below threshold. The system must report `partial` or `waiting_validation`; it must not weaken the
criteria to fill the quota.
