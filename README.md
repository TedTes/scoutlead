# ScoutLead

Reusable AI-powered customer discovery and outreach backend for validating different software products.

The product is supplied as configuration. The runtime then executes the same bounded workflow for discovery, research, qualification, outreach drafting, human approval, response tracking, memory, and campaign evaluation.

## Architecture

Application code owns deterministic workflow orchestration and allowed state transitions. The LLM is isolated behind structured-output interfaces for judgment tasks:

- research extraction
- lead qualification
- outreach personalization
- response classification

External capabilities are tools behind explicit interfaces: search, website inspection, email, and database access. Browser automation is represented as a fallback capability; first-pass inspection prefers direct HTTP.

## Discovery Data Model

ScoutLead treats public discovery results as reusable raw material, not as the product moat:

- `source_requests` preserve the user's plain-language search intent and source plan.
- Canonical businesses and contacts dedupe source results across repeated or similar searches.
- Business embeddings let semantically similar requests reuse cached contacts when an embedding provider is configured.
- `leads` remain the product/run-specific view: fit verdict, evidence, missing evidence, review state, shortlist state, draft state, approval state, and outreach history.

This keeps repeated searches cheaper while making the durable value the user's judged, verified, reviewable pipeline.

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL="postgresql://user:password@localhost:5432/scoutlead"
PYTHONPATH=agent alembic upgrade head
PYTHONPATH=agent python -m uvicorn app.main:app --reload
```

The API defaults to `http://localhost:8000` and requires `DATABASE_URL`; use Railway Postgres or another Postgres database for local development.

Run the web dashboard:

```bash
cd web
npm install
npm run dev
```

The dashboard defaults to `http://localhost:5173`.

## API Flow

Create a product:

```bash
curl -s -X POST http://localhost:8000/products \
  -H "content-type: application/json" \
  --data-binary @examples/quotevan.product.json
```

Create a campaign with the returned `product_id`:

```bash
curl -s -X POST http://localhost:8000/campaigns \
  -H "content-type: application/json" \
  -d '{"product_id":"product_xxx","max_leads":10}'
```

Run the bounded workflow:

```bash
curl -s -X POST http://localhost:8000/campaigns/campaign_xxx/run
```

Review drafts:

```bash
curl -s http://localhost:8000/campaigns/campaign_xxx/messages
```

Approve before sending:

```bash
curl -s -X POST http://localhost:8000/messages/message_xxx/approve \
  -H "content-type: application/json" \
  -d '{"approved_by":"founder@example.com"}'
```

Send an approved message:

```bash
curl -s -X POST http://localhost:8000/messages/message_xxx/send
```

Track a response:

```bash
curl -s -X POST http://localhost:8000/conversations/conversation_xxx/responses \
  -H "content-type: application/json" \
  -d '{"body":"Sure, happy to schedule an interview next week."}'
```

Measure campaign performance:

```bash
curl -s http://localhost:8000/campaigns/campaign_xxx/metrics
```

## Background Jobs

Direct endpoints are available for local development. The same operations can be queued:

```bash
curl -s -X POST http://localhost:8000/campaigns/campaign_xxx/enqueue
curl -s -X POST http://localhost:8000/messages/message_xxx/enqueue-send
soutlead-worker
```

## Railway Deployment

Create these Railway services in the same project:

1. PostgreSQL service.
2. API service from the repo root.
3. Worker service from the repo root.
4. Web service. The workflow uploads `./web` with `--path-as-root`, so the Railway service Root Directory should be `/`, not `/web`.

The repo owns service start/build settings in `deploy/railway/*.railway.json`, and the release workflow applies them before `railway up`.

Expected runtime commands after config sync:

- API and worker: `python scripts/start_railway_service.py`
- Web: `npm run preview -- --host 0.0.0.0 --port ${PORT:-4173}`

Do not use the API or worker start command on the web service. If a Railway service already has stale Build, Watch, Root Directory, or Start Command settings from earlier manual setup, clear them or let the workflow sync the values from `deploy/railway/`.

Use the examples in `deploy/railway/` for service variables. Set `AUTO_CREATE_TABLES=false` in shared environments once Alembic migrations are running. Set `API_AUTH_TOKEN` on the API and the same value as `VITE_API_TOKEN` on the web service. For user auth, set `VITE_CLERK_PUBLISHABLE_KEY` on the web service and set `REQUIRE_USER_AUTH=true` plus `CLERK_JWT_ISSUER` or `CLERK_JWKS_URL` on the API service.

### GitHub Actions Release Pipeline

The repo includes `.github/workflows/ci-release.yml`.

On pull requests, it runs backend tests and the web production build. On pushes to `main`,
it deploys the GitHub `dev` environment by default when deployable files changed. Manual
`workflow_dispatch` from `main` lets you choose either `dev` or `production`; the release
job binds to that GitHub Environment, runs Alembic against the matching Railway environment
when migrations changed, then deploys the API, worker, and web services that need updates.

Configure these GitHub repository settings before relying on the workflow. Add the same keys
under each GitHub Environment you deploy from:

- `Settings -> Environments -> dev`
- `Settings -> Environments -> production`

- Secret: `RAILWAY_TOKEN` — Railway project token scoped to the target environment.
- Secret: `RAILWAY_MIGRATION_DATABASE_URL` — Railway Postgres public connection URL for that environment.
- Variable: `RAILWAY_PROJECT_ID` — Railway project ID.
- Variable: `RAILWAY_ENVIRONMENT` — matching Railway environment name or ID, for example `dev` or `production`.
- Variable: `RAILWAY_API_SERVICE` — API service name or ID.
- Variable: `RAILWAY_WORKER_SERVICE` — worker service name or ID.
- Variable: `RAILWAY_WEB_SERVICE` — web service name or ID.

The workflow also accepts the non-token values as secrets if you stored everything in
the Secrets tab. Keep `RAILWAY_TOKEN` as a secret.

Optional:

- Secret: `RAILWAY_API_TOKEN` — Railway account/workspace token used only to sync service config if the project-scoped deploy token cannot edit Railway service settings.

Use the Postgres service's `DATABASE_PUBLIC_URL` value for `RAILWAY_MIGRATION_DATABASE_URL`.
Do not use the runtime `DATABASE_URL` if it points at `postgres.railway.internal`; GitHub
Actions runs outside Railway's private network and cannot resolve that host. The API and
worker services can still use the private `DATABASE_URL` at runtime.

Disable Railway GitHub auto-deploys for these services after the workflow is configured.
Otherwise Railway can deploy immediately on push and bypass the migration gate.

For real-world operation, disable mock providers and configure actual integrations:

```bash
ALLOW_MOCK_PROVIDERS=false
REQUIRE_REAL_SEARCH=true
REQUIRE_REAL_EMAIL=true
REQUIRE_REAL_LLM=true
REQUIRE_USER_AUTH=true
CLERK_JWT_ISSUER=https://your-clerk-issuer
CLERK_SECRET_KEY=...
SEARCH_PROVIDER=tavily # or brave
SEARCH_API_KEY=...
OPENAI_API_KEY=...
EMAIL_PROVIDER=gmail
EMAIL_FROM_ADDRESS=founder@example.com
EMAIL_FROM_NAME=ScoutLead
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=https://replace-with-api-service-domain.up.railway.app/email/gmail/callback
GOOGLE_OAUTH_STATE_SECRET=...
GOOGLE_TOKEN_ENCRYPTION_KEY=...
CONTACT_VERIFICATION_PROVIDER=bouncer
BOUNCER_API_KEY=...
GOOGLE_PLACES_API_KEY=...
APIFY_API_TOKEN=...
APIFY_SOURCE_KIJIJI={"id":"kijiji","label":"Kijiji","enabled":true,"actor_id":"actor-owner/kijiji-actor","input_kind":"text_query","input_template":{"query":"{{query}}","maxResults":"{{limit}}"}}
APIFY_SOURCE_HOMESTARS={"id":"homestars","label":"HomeStars","enabled":true,"actor_id":"actor-owner/homestars-actor","input_kind":"text_query","input_template":{"query":"{{query}}","maxResults":"{{limit}}"}}
```

If you use Resend instead of Gmail, set `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, and a verified `EMAIL_FROM_ADDRESS`.

Use one `APIFY_SOURCE_<NAME>` env var per Apify-backed source. The suffix must match the object `id`, so `APIFY_SOURCE_KIJIJI` maps to source id `kijiji`. Each source must define an `input_template` or URL template that matches that actor's expected input shape; ScoutLead interprets the user's plain-language request once, then renders that source-specific template. Template values include `{{query}}`, `{{business_category}}`, `{{business_slug}}`, `{{location}}`, `{{location_slug}}`, `{{city}}`, `{{region}}`, `{{country}}`, `{{limit}}`, and `{{source_url}}`. The old `APIFY_SOURCES` array is still read only when no per-source env vars are present.

Set `CONTACT_VERIFICATION_PROVIDER=bouncer` to verify discovered email addresses through Bouncer before drafts can be generated. The verifier is provider-backed, so `syntax`, generic `http`, and `zerobounce` remain available for local/testing or future swaps.

Before running a campaign, check provider readiness:

```bash
curl -s http://localhost:8000/campaigns/campaign_xxx/preflight
```

If required providers are missing, the API blocks campaign runs before creating an agent run.

## Product Payload Shape

```json
{
  "product_name": "<your product name>",
  "product_description": "<what the product does>",
  "target_customer": "<who you want to validate with>",
  "problem_being_solved": "<problem being validated>",
  "value_proposition": "<why the product matters>",
  "target_geography": "<target geography>",
  "validation_goal": "<validation goal>",
  "qualification_criteria": [
    { "label": "<required customer signal>", "weight": 3, "required": true },
    { "label": "<useful customer signal>", "weight": 2 }
  ],
  "preferred_discovery_sources": [
    { "type": "web_search", "value": "<real search query or source>" }
  ],
  "outreach_objective": "<outreach objective>",
  "constraints": ["<campaign constraint>"]
}
```

Campaigns can also include `discovery_seeds` when no search provider is configured.

## Verification

```bash
python -m compileall agent
pytest -q
cd web && npm run build
```

For a browser and deployment checklist, see `docs/manual-e2e-test.md`.
