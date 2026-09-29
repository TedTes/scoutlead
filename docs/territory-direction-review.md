# ScoutLead Territory Direction Review

## Purpose

This document gives Claude Code the product and implementation context needed to review ScoutLead's current direction. Review the claims against the repository and identify inconsistencies, missing behavior, duplicated concepts, and migration risks.

Do not redesign the interface based only on this document. First inspect the relevant backend models, services, routes, migrations, frontend navigation, and screens.

## Business direction

ScoutLead is moving from a one-off customer-discovery and lead-search tool toward a recurring local prospecting product.

The target customer is a business that repeatedly sells to local businesses, such as suppliers, agencies, software companies, insurance brokers, and service firms.

The intended promise is:

> Define what you sell and the local markets you want to cover. ScoutLead regularly delivers new businesses that fit, explains the supporting evidence, identifies the best available contact channel, and improves ranking as outcomes are recorded.

The one-off search workflow remains relevant, but becomes a secondary **Explore** workflow. Recurring prospecting is organized around saved territories.

## Proposed product hierarchy

```text
Sales profile
  -> Territories
    -> Deliveries
      -> Qualified contacts
        -> Outcomes
```

### Sales profile

A sales profile describes the seller's commercial context:

- What the business sells
- The kinds of businesses it wants as customers
- Observable signs of a good fit
- Explicit exclusions
- Default geography
- Qualification criteria
- Outreach context

The existing backend continues to use the `products` table, product schemas, and `/products` API paths. The new direction changes the user-facing meaning rather than requiring an immediate backend rename.

The UI previously used **Product**, then **Offer**. Neither label fully communicates that this object combines the seller's service, ideal customer profile, qualification policy, and outreach context. The current candidate label is **Sales profile**.

Example:

```text
Sales profile: Commercial insurance for independent contractors
```

### Territory

A territory is a recurring prospecting market under one sales profile. It combines:

- One sales profile
- One business niche
- One geographic market
- Refresh cadence
- Delivery size
- Minimum fit threshold

Examples under the sales profile above:

```text
HVAC contractors in Toronto
Roofing contractors in Mississauga
Plumbing companies in Hamilton
```

The sales profile defines **what qualifies and why**. A territory defines **where and among which type of businesses ScoutLead should repeatedly search**.

The same niche and city may be used under multiple sales profiles because fit criteria and outreach context can differ.

### Delivery

A delivery is one dated refresh of a territory. It is backed by a discovery run and should contain businesses not previously delivered for the same workspace and sales profile.

The intended refresh behavior is:

1. Search the canonical niche pool first.
2. Exclude businesses already delivered for the sales profile.
3. Use live public sources when cached candidates cannot fill the batch.
4. Research, qualify, and verify candidates.
5. Keep contacts at or above the territory's minimum fit threshold.
6. Rank the resulting contacts and create the delivery.

### Qualified contact

A qualified contact combines the business record with:

- Fit verdict and score
- Supporting evidence
- Controlled signal tags
- Contact readiness
- Source quality
- Best deterministic contact channel
- Evidence-grounded opener or talk track
- Latest outcome

Fit and reachability are separate concepts. Contact availability must not be treated as proof that a business is a good customer.

### Outcome

Outcomes record what happened after delivery or contact:

- Contacted
- No response
- Positive reply
- Negative reply
- Meeting booked
- Won
- Not a fit
- Wrong contact
- Business closed
- Bounced
- Unsubscribed

Commercial outcomes remain workspace-scoped. Objective data-quality outcomes may update canonical contact or business data.

Once enough outcomes exist for a workspace, sales profile, and niche, controlled signal tags can adjust future ranking. Outcome learning must not change a fit verdict or promote a `not_fit` lead.

## Intended user workflow

1. The user creates a sales profile describing what they sell and who should buy it.
2. The user creates a territory with one input such as `HVAC contractors in Toronto`.
3. ScoutLead resolves the niche and market and asks the user to confirm them.
4. The user runs the first refresh or enables recurring refreshes.
5. ScoutLead returns a deduplicated delivery of qualified contacts.
6. The user reviews evidence, contact channel, and suggested approach.
7. The user exports a call sheet or sends selected outreach through Gmail.
8. The user records replies, meetings, wins, fit errors, and data problems.
9. Territory metrics show contact, reply, meeting, win, quality, and outcome-coverage rates.
10. Later deliveries use accumulated outcomes to improve ranking.

The **Explore** workflow remains for ad hoc searches that should not become a recurring territory.

## Current implementation

The repository currently contains or partially contains the following territory-direction work:

- Additional sales-profile fields on the existing product model
- Territory and territory-delivery models and migrations
- Territory resolve, create, update, refresh, delivery, metrics, and export APIs
- Feature flags for the territory UI and scheduler
- Cached-first discovery and previously-delivered business exclusion
- Workspace sender identity
- Signed unsubscribe links and workspace suppression
- Daily send limits
- Immutable lead outcomes and denormalized latest outcome fields
- Automatic no-response maintenance
- Controlled niche signal vocabularies
- Deterministic best-channel selection
- LLM-generated evidence-grounded approaches
- Outcome-learning snapshots and rank adjustments
- Territory metrics and CSV exports
- A territory-first frontend screen
- One-off Explore and run history retained alongside Territories

Relevant areas include:

```text
agent/db/models.py
agent/db/migrations/versions/20260928_*.py
agent/products/
agent/territories/
agent/outcomes/
agent/evaluation/outcome_learning.py
agent/evaluation/outcome_learning_service.py
agent/leads/approach_service.py
agent/unsubscribe/
agent/workspaces/
agent/job_queue/worker.py
agent/workflows/discovery.py
web/src/screens/TerritoriesScreen.tsx
web/src/screens/ProductScreen.tsx
web/src/screens/ResultsScreen.tsx
web/src/screens/IntegrationsScreen.tsx
web/src/app/navigation.tsx
web/src/app/App.tsx
```

## Known terminology inconsistency

The backend object is still named `Product`, while frontend copy currently mixes or has recently mixed:

- Product
- Offer
- Sales profile

Review all visible strings and determine where terminology is inconsistent. Do not recommend a database or API rename unless the benefit justifies the migration and compatibility cost.

The intended user-facing hierarchy for review is:

```text
Sales profiles -> Territories -> Deliveries -> Contacts -> Outcomes
```

## Questions for Claude Code

Review the repository and report on the following:

1. Does the implemented data model accurately enforce the hierarchy between sales profiles, territories, deliveries, contacts, and outcomes?
2. Can a territory or delivery accidentally access another workspace's data?
3. Is previously delivered business deduplication correctly scoped to workspace and sales profile across all territories?
4. Does territory refresh actually follow cached-first then live-source top-up behavior?
5. Are qualification, reachability, source quality, and outcome-adjusted rank kept separate throughout the backend and UI?
6. Are deterministic policies responsible for state transitions and sending decisions, with the LLM limited to structured judgment and writing?
7. Does every lead created for a territory receive the correct `territory_id`?
8. Are outcomes immutable, correctly scoped, and safe to use for learning?
9. Can outcome learning leak data between workspaces, sales profiles, niches, or future holdout periods?
10. Does a territory delivery sort by `rank_score` without promoting `not_fit` contacts?
11. Are sender identity, suppression, unsubscribe, and send-cap rules enforced on every outbound path?
12. Does the frontend make the relationship between a sales profile and its territories understandable?
13. Is Explore clearly secondary without making existing run history inaccessible?
14. Which legacy customer-discovery concepts still conflict with the territory model?
15. Which implemented features are backend-only or unreachable from the frontend?
16. Which paths are incomplete, misleading, or only partially covered by tests?
17. Are all migrations reversible and safe for the existing production schema?
18. Is the territory scheduler idempotent under multiple workers or process restarts?
19. Are automatic no-response and outcome-model recomputation jobs safe to run repeatedly?
20. What is the smallest set of corrections required before a real pilot?

## Expected review format

Return findings first, ordered by severity:

```text
Severity
File and line
Observed behavior
Why it matters
Recommended correction
Missing or existing test coverage
```

Then provide:

- A concise architecture assessment
- A list of terminology inconsistencies
- A list of unreachable or incomplete features
- A pilot-readiness assessment
- A prioritized correction sequence

Do not implement changes during this review. Do not infer behavior from names alone; trace routes through services, repositories, models, and frontend callers.
