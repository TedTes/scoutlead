# Website assessment model

ScoutLead's website assessment is deliberately split into four layers:

1. Stored website evidence is converted into a stable numeric feature contract.
2. An interchangeable model predicts upgrade probability, confidence, and reasons.
3. The prediction is stored as `website_upgrade_assessment` in `business_attributes`.
4. Human labels are stored separately as `website_upgrade_training_label`.

The default model is a dependency-free linear baseline. It is not a production
eligibility gate. Assessments are written with `mode: shadow`, so they can be
compared with human labels before they affect search results. A later vision,
embedding, scikit-learn, or XGBoost implementation only needs to implement the
`WebsiteAssessmentModel` protocol; the API and feature contract stay unchanged.

## Admin workflow

Open a business in Admin and use the **Website model** tab to:

- run the local assessment from already stored evidence;
- record one of `strong`, `acceptable`, `upgrade_candidate`, or `broken`;
- select observable reasons and add notes;
- attach desktop and mobile screenshot references.

Running an assessment does not fetch the website and does not call a paid API.

## Local browser capture

Install the optional local runtime once:

```bash
pip install -e '.[website-capture]'
playwright install chromium
```

Capture one or more stored business websites without cloud infrastructure:

```bash
PYTHONPATH=agent python scripts/capture_websites.py \
  --business-id business_123 \
  --artifact-root artifacts/website-captures
```

Fresh captures are reused for seven days by default. Pass `--force` when a
business website must be recaptured immediately. The window is configurable
with `WEBSITE_CAPTURE_FRESHNESS_DAYS`.

The capture worker:

- blocks private/local network destinations;
- captures desktop and mobile screenshots;
- measures layout overflow, tap-target size, broken images, headings, and basic page structure;
- stores binary artifacts on the local filesystem in development or private S3-compatible storage
  in deployed environments;
- stores only a compact manifest in `business_attributes`;
- reruns the model-independent shadow assessment after capture.

Admin can enqueue the same `website.capture` job from the **Website model** tab.
`ArtifactStore`, `BrowserCaptureProvider`, and `WebsiteVisionModel` are protocols, so a hosted
vision model can be added later without changing the queue, admin API, or assessment service.

The API, worker, and web runtime images are separate. `Dockerfile.worker` installs Playwright and
Chromium; the API and web images do not carry browser dependencies. The worker is sequential and
must remain at one Railway replica during the initial capture rollout.

Configure persistent storage on the worker with `WEBSITE_CAPTURE_STORAGE_BACKEND=s3` and the
`WEBSITE_CAPTURE_S3_*` variables documented in `deploy/railway/worker.env.example`. The adapter is
compatible with AWS S3, R2, and other S3-compatible object stores. Bucket creation, credentials,
deployment, and the first production capture are intentionally not automated by this repository.

## Dataset and training

Export labels and features:

```bash
PYTHONPATH=agent python scripts/export_website_assessment_dataset.py \
  --output website-assessment-dataset.json
```

Train the local logistic baseline:

```bash
PYTHONPATH=agent python scripts/train_website_assessment_model.py \
  --input website-assessment-dataset.json \
  --output website-assessment-model.json \
  --version trained-1
```

Use the trained model by setting:

```text
WEBSITE_ASSESSMENT_MODEL_PATH=/absolute/path/website-assessment-model.json
```

Assess stored businesses without network access:

```bash
PYTHONPATH=agent python scripts/assess_websites.py --limit 100
PYTHONPATH=agent python scripts/assess_websites.py --limit 100 --persist
```

The first command is a dry run. The second persists assessment attributes.

## Promotion rule

Do not use this model as a hard filter. First collect a representative labeled
set across trades, split evaluation by business (and preferably by trade), and
measure precision among the top-ranked candidates. Promote it to ranking only
after it consistently improves that metric over the current evidence score.
