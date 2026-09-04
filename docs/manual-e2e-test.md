# ScoutLead Manual End-to-End Test

Use this checklist when validating the full discovery, qualification, export, and outreach flow.

## Local Preflight

1. Install backend dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. Configure a Postgres database and run migrations:

   ```bash
   export DATABASE_URL="postgresql://user:password@localhost:5432/scoutlead"
   PYTHONPATH=agent alembic upgrade head
   ```

3. Start the API:

   ```bash
   PYTHONPATH=agent python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

4. Start the worker in a second shell:

   ```bash
   PYTHONPATH=agent python -m job_queue.worker
   ```

5. Start the web app in a third shell:

   ```bash
   cd web
   npm install
   npm run dev
   ```

## Automated Checks

Run these before a release:

```bash
python -m compileall agent
pytest -q
cd web && npm run build
git diff --check
```

## Browser Flow

1. Open the Vite app, usually `http://localhost:5173`.
2. Create or select a product.
3. Open Product settings and confirm edits autosave after changing the product description or focus hints.
4. Create a new discovery run from the finder screen.
5. Use a concrete local-business prompt, for example:

   ```text
   independent residential painters in Toronto with a website, quote form, and owner contact
   ```

6. Submit the run and confirm the run history item stays visible after refresh.
7. Wait for results to finish and confirm the counts update: found, reachable, verified, good fit, shortlisted, drafted, approved.
8. Check the result controls:
   - Stage tabs: All, Shortlisted, Needs review.
   - Filter dropdown: Good fit, Verified, Has draft, Not fit.
   - Sort dropdown: Contact, Score, Name.
9. Open a contact drawer and confirm:
   - Overview shows address, website, contact, email, phone, metrics, and activity.
   - Evidence shows verification and fit evidence.
   - Outreach shows draft generation, approval, and send controls.
10. Mark one lead Shortlist and one Pass. Confirm the list and drawer reflect the state.
11. Generate a draft for a shortlisted, verified, allowed lead.
12. Approve the draft. Only test sending after Gmail is connected and you are using a safe recipient.
13. Use Export all contacts and confirm the filename dialog appears before CSV download.

## Gmail Setup Check

1. In Google Cloud OAuth, add the API callback URI:

   ```text
   https://<api-host>/email/gmail/callback
   ```

2. Configure API and worker environment variables:

   ```bash
   EMAIL_PROVIDER=gmail
   GOOGLE_OAUTH_CLIENT_ID=...
   GOOGLE_OAUTH_CLIENT_SECRET=...
   GOOGLE_OAUTH_REDIRECT_URI=https://<api-host>/email/gmail/callback
   GOOGLE_OAUTH_STATE_SECRET=...
   GOOGLE_TOKEN_ENCRYPTION_KEY=...
   EMAIL_FROM_ADDRESS=you@your-domain.com
   EMAIL_FROM_NAME=ScoutLead
   ```

3. If the Google OAuth consent screen is still in Testing, add the Gmail account as a test user.
4. Open Integrations, connect Gmail, and verify the connected email appears.
5. Send only approved outreach. Suppressed, unverified, unreachable, or not-fit leads should stay blocked.

## External Providers

For a real discovery run, configure:

- `OPENAI_API_KEY`
- `GOOGLE_PLACES_API_KEY`
- `APIFY_API_TOKEN` and at least one `APIFY_SOURCE_<NAME>`
- `CONTACT_VERIFICATION_PROVIDER=bouncer`
- `BOUNCER_API_KEY`
- Gmail variables from the section above, or Resend variables if `EMAIL_PROVIDER=resend`

Run the campaign preflight endpoint before a live run:

```bash
curl -s http://localhost:8000/campaigns/<campaign_id>/preflight
```

## Railway Release Check

1. Disable Railway GitHub auto-deploys for API, worker, and web services.
2. In GitHub, configure each environment you deploy from, for example `dev` and `production`.
3. Add environment secrets/variables:
   - `RAILWAY_TOKEN`
   - `RAILWAY_PROJECT_ID`
   - `RAILWAY_ENVIRONMENT`
   - `RAILWAY_API_SERVICE`
   - `RAILWAY_WORKER_SERVICE`
   - `RAILWAY_WEB_SERVICE`
   - `RAILWAY_MIGRATION_DATABASE_URL`
4. Use Railway Postgres `DATABASE_PUBLIC_URL` for `RAILWAY_MIGRATION_DATABASE_URL`; GitHub Actions cannot reach `postgres.railway.internal`.
5. Keep runtime `DATABASE_URL` inside Railway services pointed at the private Railway Postgres reference variable.
6. Use `RAILWAY_API_TOKEN` only if the deploy token cannot sync service config.
7. Push to `main` to deploy `dev`, or run the workflow manually from `main` and choose `production`.
8. Confirm the workflow applies service config, runs migrations when needed, and deploys only services whose watch paths changed.
