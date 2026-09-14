# Claude Code Prompt: Bulk Outreach UI

You are working in the ScoutLead codebase.

Context:
- ScoutLead fetches local businesses for a discovery run, scores whether each business fits the selected product, shows contact readiness, and lets the user manually approve outreach.
- The current app already supports per-contact review, per-contact draft creation, per-message approval, and per-message sending.
- A new backend/API layer has been added for campaign-level outreach so the user can write one base email and prepare personalized drafts for multiple businesses at once.
- The requirement is to implement the UI/UX for this new bulk outreach flow.

Existing backend endpoints:
- `POST /discovery-runs/{run_id}/campaign-drafts`
- `POST /discovery-runs/{run_id}/campaign-drafts/approve`
- `POST /discovery-runs/{run_id}/campaign-drafts/send`

Existing frontend app-data methods:
- `createCampaignOutreachDrafts(input, runId?)`
- `approveCampaignOutreachDrafts(input?, runId?)`
- `sendCampaignOutreachDrafts(input?, runId?)`

Existing frontend types:
- `CampaignOutreachDraftInput`
- `CampaignOutreachAudience`
- `CampaignMessageBatchResult`
- `CampaignMessageSkip`

Backend behavior:
- `createCampaignOutreachDrafts` accepts:
  - `audience`: `"ready_contacts"`, `"ready_shortlist"`, or `"selected"`
  - `lead_ids`: required only when `audience` is `"selected"`
  - `subject`
  - `body`
  - optional `approach_tag`
- The backend creates one message draft per eligible business.
- Existing pending/approved/sent messages are reused instead of duplicated.
- Ineligible contacts are returned in `skipped` with a reason.
- Sending still requires prior approval. Calling bulk send on pending drafts returns skipped results instead of sending them.

Supported template tokens:
- `{{business_name}}`
- `{{company_name}}`
- `{{recipient_name}}`
- `{{contact_name}}`
- `{{geography}}`
- `{{service_area}}`
- `{{fit_reason}}`
- `{{website_url}}`
- `{{product_name}}`
- `{{product_description}}`
- `{{value_proposition}}`
- `{{problem}}`
- `{{outreach_objective}}`

Implementation task:
- Add the UI needed for a user to prepare one outreach email for multiple fetched businesses.
- The user should be able to enter/edit the base subject and body.
- The user should be able to choose between all ready contacts and selected contacts.
- The UI should call `createCampaignOutreachDrafts` to prepare drafts.
- After drafts are prepared, the UI should expose approval using `approveCampaignOutreachDrafts`.
- After approval, the UI should expose sending using `sendCampaignOutreachDrafts`.
- Show counts returned by the API, including created, reused, approved, sent, failed, and skipped.
- Show skipped contacts and their reasons somewhere in the flow.
- Use the existing toast/error patterns already present in the app.
- Preserve the existing per-contact workflow.

Validation:
- Run the frontend build.
- Confirm the new UI compiles against the existing app-data methods and types.
- Confirm no backend contract changes are needed.
- Confirm the flow does not send emails before approval.
