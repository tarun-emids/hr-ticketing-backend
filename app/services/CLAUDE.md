# CLAUDE.md — services

Business rules only: no database access, no HTTP beyond domain responses.

## Contract

- Raise `HTTPException` **only** for domain responses the API owns:
  404 (unknown ticket/draft/notification), 409 (conflict, e.g. wrong
  lifecycle state), 422 (validation / unknown user), 413 (file too large),
  403 (auth account activation gaps). Dependency failures surface from
  repositories as
  400/502/503 — don't re-map them here, and don't catch-and-reword them.
- Repositories arrive injected (app/deps.py). Never import app.config or
  resolve a client inside a service — that breaks the offline test harness.
- Semantics and shapes mirror the frontend store.js; camelCase in/out at
  the HTTP boundary belongs to models.py serializers, not service dicts.
- The single behavior fork: agent replies stamp `firstReplyAt` once and
  move Open → In Progress; employee replies flip an active ticket to
  Waiting on Employee; assigning an unanswered ticket auto-posts the agent
  pickup reply. Reuse `TicketService.assign` rather than duplicating any
  of that.

## Notifications

- Write first, notify after: services call
  `notifier.safe_notify(event, ticket, actor, recipients(...))` only AFTER
  the ticket write completes. `safe_notify` swallows and logs failures —
  a broken notification path can never break a ticket action.
- **Privacy rule (hard):** generic messages only — actor name + ticket ref
  ("Alicia Gomez resolved TKT-104"). Never include ticket subject,
  description or reply body.
- Recipient rules and `EV_*` message branches are pure functions,
  unit-tested in tests/unit/test_notification_rules.py; the event matrix
  lives in README §10.
- Background jobs (`run_sla_sweep`, `run_retention_cleanup`) swallow their
  own errors and are scheduled by main.py's lifespan every
  `SLA_SWEEP_INTERVAL_SECONDS`; SLA thresholds "at most once per
  ticket/threshold" are enforced via notification payloads.

## Authentication (AuthService)

- Login loads the account's scrypt password hash through `UserRepository`;
  never log passwords, hashes, or return `password_hash` in an API response.
- Use the generic invalid-credentials response for missing users, unprovisioned
  accounts, and wrong passwords.
- Password provisioning is an operations script; there is no public signup.
  PostgreSQL errors pass through the shared database breaker.
