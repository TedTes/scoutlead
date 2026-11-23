# Railway service config

Railway has three deployable ScoutLead services:

- API: Python app from the repo root using `Dockerfile.api`.
- Worker: Python background worker using `Dockerfile.worker`, which alone contains
  Playwright, Chromium, and the S3 client.
- Web: Vite app deployed from `./web --path-as-root` using `web/Dockerfile`.

The release workflow applies service settings from this directory before running `railway up`.
The legacy root Dockerfile remains as a local/backward-compatible image. Railway service manifests
select the dedicated images through `build.dockerfilePath`.

Changes in this directory intentionally trigger the full Railway release path.

## Runtime commands

API:

```sh
python scripts/start_railway_service.py
```

Worker:

```sh
python scripts/start_railway_service.py
```

The worker loop claims and executes one queue job at a time. Keep the Railway worker service at one
replica while browser capture is enabled; horizontal worker scaling would allow separate capture
jobs to run concurrently.

Web:

```sh
node server.mjs
```

`server.mjs` is a dependency-free static file server that serves `dist/` with SPA fallback.
It's invoked directly (not via `npm run start`) because Railway's runtime container does not
include `npm`, only `node`. It replaced `vite preview` because `vite preview` is a dev-oriented
server not intended for production hosting.

The startup script uses `SCOUTLEAD_SERVICE` or `SERVICE_TYPE` when present. Otherwise it falls back
to Railway's `RAILWAY_SERVICE_NAME`; service names containing `worker` run the worker, service
names containing `web` or `front` serve the built frontend, and all other names run the API.

## Website capture storage

Local development defaults to `WEBSITE_CAPTURE_STORAGE_BACKEND=local`. A deployed worker should
use a private S3-compatible bucket:

```text
WEBSITE_CAPTURE_STORAGE_BACKEND=s3
WEBSITE_CAPTURE_S3_BUCKET=<bucket>
WEBSITE_CAPTURE_S3_PREFIX=website-captures
WEBSITE_CAPTURE_S3_ENDPOINT_URL=<provider endpoint, when required>
WEBSITE_CAPTURE_S3_REGION=<region, when required>
WEBSITE_CAPTURE_S3_ACCESS_KEY_ID=<secret>
WEBSITE_CAPTURE_S3_SECRET_ACCESS_KEY=<secret>
```

Only the worker needs these credentials. PostgreSQL stores `s3://` object references and compact
capture metrics, never screenshot bytes. Creating the bucket and configuring secrets remain manual
deployment steps.

The web workflow uses `--path-as-root`, so the uploaded archive root is the `web` directory itself.
For that reason the web service root directory is `/`, not `/web`.

## GitHub release environment

Each GitHub environment that deploys to Railway needs these values:

- `RAILWAY_TOKEN`
- `RAILWAY_PROJECT_ID`
- `RAILWAY_ENVIRONMENT`
- `RAILWAY_API_SERVICE`
- `RAILWAY_WORKER_SERVICE`
- `RAILWAY_WEB_SERVICE`
- `RAILWAY_MIGRATION_DATABASE_URL`

Optional:

- `RAILWAY_API_TOKEN` for the service-config sync step if the project-scoped `RAILWAY_TOKEN`
  cannot edit Railway service settings.

`RAILWAY_MIGRATION_DATABASE_URL` must use the public Postgres URL because GitHub Actions is
outside Railway's private network. Runtime `DATABASE_URL` inside Railway services should use the
private Railway Postgres reference variable.

## Notes

Railway's current CLI supports setting service root directories and start commands with
`railway environment edit --service-config`. The workflow uses `RAILWAY_PROJECT_ID` directly and
does not call `railway link`, so project-scoped CI tokens do not need interactive linking
permissions. If service-config edits need broader access, add `RAILWAY_API_TOKEN`; the workflow
will use it only for config sync and will keep `RAILWAY_TOKEN` for deploys. Config-as-code files
are still documented by Railway, but Railway marks
`railway.json` / `railway.toml` config-as-code as deprecated for new services, so the workflow
applies these manifest values through the CLI instead of relying on automatic file discovery.
