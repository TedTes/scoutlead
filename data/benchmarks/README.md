# Business accuracy benchmark

Generate a deterministic, stratified draft from businesses already in the configured database:

```bash
python scripts/business_benchmark.py sample \
  --output data/benchmarks/business-accuracy-v1.local.jsonl \
  --market toronto \
  --per-niche 50
```

Review each record and fill `labels`. A record becomes reviewed when it has both `reviewer`
and `reviewed_at`. Keep `unknown` when the available public evidence does not establish a fact.
Do not convert a missing value into `no`.

Evaluate the reviewed file:

```bash
python scripts/business_benchmark.py evaluate \
  --input data/benchmarks/business-accuracy-v1.local.jsonl \
  --output data/benchmarks/business-accuracy-v1.report.local.json \
  --require-niche home_service_painting \
  --require-market toronto
```

The default release gate requires 200 reviewed businesses, at least 50 labels for each
measured property, and at least 30 reviewed records in every explicitly required niche or
market. It also enforces the precision thresholds in `benchmarks.evaluator`. A small perfect
sample is not sufficient to approve another trade or market.

Local benchmark exports are intentionally ignored because they contain public business contact
data. Reviewed benchmark artifacts should be stored in an access-controlled data location.
