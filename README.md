# soutlead

Reusable AI-powered customer discovery and outreach backend for validating different software products.

The product is supplied as configuration. The runtime then executes the same bounded workflow for discovery, research, qualification, outreach drafting, human approval, response tracking, memory, and campaign evaluation.

## Architecture

Application code owns deterministic workflow orchestration and allowed state transitions. The LLM is isolated behind structured-output interfaces for judgment tasks:

- research extraction
- lead qualification
- outreach personalization
- response classification

External capabilities are tools behind explicit interfaces: search, website inspection, email, and database access. Browser automation is represented as a fallback capability; first-pass inspection prefers direct HTTP.

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL="postgresql://user:password@localhost:5432/soutlead"
PYTHONPATH=agent uvicorn app.main:app --reload
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

## Railway MVP Deployment

Create these Railway services from the same GitHub repo:

1. PostgreSQL service.
2. Backend service from repo root.
3. Worker service from repo root.
4. Web service from `web/`.

Backend start command:

```bash
PYTHONPATH=agent uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Worker start command:

```bash
PYTHONPATH=agent python -m queue.worker
```

Web build/start commands:

```bash
npm ci
npm run build
npm run preview -- --host 0.0.0.0 --port $PORT
```

Set the web service Root Directory to:

```text
/web
```

Do not use the backend start command on the web service.

Run migrations before disabling table auto-creation:

```bash
PYTHONPATH=agent DATABASE_URL="$DATABASE_URL" alembic upgrade head
```

Use the examples in `deploy/railway/` for service variables. Set `AUTO_CREATE_TABLES=false` in production after migrations are running. Set `API_AUTH_TOKEN` on the backend and the same value as `VITE_API_TOKEN` on the web service.

For real-world operation, disable mock providers and configure actual integrations:

```bash
ALLOW_MOCK_PROVIDERS=false
REQUIRE_REAL_SEARCH=true
REQUIRE_REAL_EMAIL=true
REQUIRE_REAL_LLM=true
SEARCH_PROVIDER=tavily # or brave
SEARCH_API_KEY=...
OPENAI_API_KEY=...
EMAIL_PROVIDER=resend
RESEND_API_KEY=...
EMAIL_FROM_ADDRESS=founder@example.com
GOOGLE_PLACES_API_KEY=...
APIFY_API_TOKEN=...
APIFY_SOURCES=[{"id":"kijiji","label":"Kijiji","actor_id":"actor-owner/kijiji-actor"},{"id":"homestars","label":"HomeStars","actor_id":"actor-owner/homestars-actor"}]
```

Use `APIFY_SOURCES` when more than one Apify-backed source is available. Each item becomes a selectable source provider by its `id`; the legacy single-source `APIFY_ACTOR_ID` style remains supported for older deployments.

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
