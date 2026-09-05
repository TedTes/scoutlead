# Railway service config

Railway has three deployable ScoutLead services:

- API: Python app from the repo root using the root `Dockerfile`.
- Worker: Python background worker from the repo root using the root `Dockerfile`.
- Web: Vite app deployed from `./web --path-as-root`.

The release workflow applies service settings from this directory before running `railway up`.
The backend services also ship with a root Dockerfile so Railway does not need to infer their
Python start command during Railpack prepare.

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

Web:

```sh
node server.mjs
```

`server.mjs` is a dependency-free static file server that serves `dist/` with SPA fallback.
It's invoked directly (not via `npm run start`) because Railway's runtime container does not
include `npm`, only `node`. It replaced `vite preview` because `vite preview` is a dev-oriented
server not intended for production hosting.

The backend startup script uses `SCOUTLEAD_SERVICE` or `SERVICE_TYPE` when present. Otherwise it
falls back to Railway's `RAILWAY_SERVICE_NAME`; service names containing `worker` run the worker,
and all other backend service names run the API.

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
