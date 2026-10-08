# CLAUDE.md — services

Business rules only: no Supabase access, no HTTP beyond domain responses.

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

## External auth surface (AuthService)

- `_grant()` deliberately creates a fresh throwaway client per password
  grant: `sign_in_with_password` stores the USER session on whichever
  client ran it, and supabase-py would then send that user's JWT on later
  `.table()` reads. public.users has RLS deny-all, so the service-key
  singleton must stay clean or reads silently return [] (this was a real
  bug). Keep the per-grant pattern; never grant on `get_client()`.
- The grant runs behind `auth_breaker` with `_auth_failure` classification:
  answered grant errors (status < 500) are NEUTRAL; transport errors and
  auth 5xx count. `login()` translates `CircuitOpenError` to its own 503
  before the generic handler can see it.
