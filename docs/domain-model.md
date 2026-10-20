# Domain model

This document defines the canonical product vocabulary and the ownership and
provenance boundaries implemented by the application.

## Audience

**Audience** is the product term for a saved business-search definition. It
contains the offer, niche, market, services, opportunity signals, exclusions,
schedule, and refill policy.

The current database table and Python implementation retain the historical
`territories`/`Territory*` names to avoid a high-risk physical rename. Public
UI and API paths use **Audience**. `Profile` is reserved for actual user,
sender, or product profiles and must not be introduced as another synonym for
an audience.

```text
Audience (database: territories)
└── AudienceRun
    └── AudienceResult
        └── Business
```

Canonical audience APIs are under `/audiences`; the former `/territories` and
`/profiles` public routes have been removed.

## Outreach

Outreach packages and messages have different responsibilities:

```text
AudienceResult
└── OutreachPackage          generated and editable channel recommendations
    └── Message              immutable snapshot entering approval/send flow
        └── Conversation
            └── ConversationEvent
```

- `outreach_packages` owns generated content, alternatives, and editor events.
- `messages` owns the exact approved/sent content and provider delivery state.
- `conversations` and `conversation_events` own actual correspondence.
- `messages.outreach_package_id` preserves the handoff and prevents more than
  one message from being created from the same package.

Copying content for manual use remains a package event. Preparing an email for
in-app delivery snapshots the saved package into a message; later package
edits do not silently alter that message.

## Evidence and provenance

The evidence model is branched rather than a single foreign-key chain:

```text
SourceItem ──business_id──────────────┐
    └── SourceItemDecision            │
        └── observation id in details │
                                      ▼
Business ──→ SourceObservation ──→ FactClaim
                  │                    │
                  │                    └── resolver ──→ BusinessFact
                  │                                      │
                  └──────────────────────────────────────→ BusinessFactChange
```

`BusinessFact.supporting_claim_ids` is a JSON provenance list, not a database
foreign key. `BusinessFactChange` is an append-only value-change record keyed
by `business_id` and `fact_key`; it does not own or replace the current fact.

## Personal workspace ownership

A workspace is the account-level data boundary, not a product and not a team:

```text
User
└── Personal Workspace
    ├── Product
    ├── Audience
    ├── Campaign
    └── Outreach data
```

`workspaces.owner_user_id` records personal ownership. Repository
`workspace_id` filters remain mandatory because they prevent one account from
reading another account's data. Shared membership and role-based permissions
are intentionally not part of the current product.
