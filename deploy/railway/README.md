# Railway service config

Railway has three deployable ScoutLead services:

- API: Python app from the repo root.
- Worker: Python background worker from the repo root.
- Web: Vite app with Railway root directory `/web`.

The release workflow applies the critical service settings from this directory before running
`railway up`. This prevents dashboard drift, especially the worker failure where Railpack cannot
infer a start command.

## Runtime commands

API:

```sh
PYTHONPATH=agent python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Worker:

```sh
PYTHONPATH=agent python -m job_queue.worker
```

Web:

```sh
npm run preview -- --host 0.0.0.0 --port ${PORT:-4173}
```

## GitHub release environment

Each GitHub environment that deploys to Railway needs these values:

- `RAILWAY_TOKEN`
- `RAILWAY_PROJECT_ID`
- `RAILWAY_ENVIRONMENT`
- `RAILWAY_API_SERVICE`
- `RAILWAY_WORKER_SERVICE`
- `RAILWAY_WEB_SERVICE`
- `RAILWAY_MIGRATION_DATABASE_URL`

`RAILWAY_MIGRATION_DATABASE_URL` must use the public Postgres URL because GitHub Actions is
outside Railway's private network. Runtime `DATABASE_URL` inside Railway services should use the
private Railway Postgres reference variable.

## Notes

Railway's current CLI supports setting service root directories and start commands with
`railway environment edit --service-config`. Config-as-code files are still documented by Railway,
but Railway marks `railway.json` / `railway.toml` config-as-code as deprecated for new services, so
the workflow applies these manifest values through the CLI instead of relying on automatic file
discovery.
