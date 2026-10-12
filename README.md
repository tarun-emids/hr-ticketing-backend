# HR Desk API — FastAPI + Supabase backend

FastAPI backend that persists the HR ticketing data in **Supabase (Postgres + Storage)**.
Endpoint shapes mirror `src/data/store.js` 1:1 so the React frontend can swap the
mock store for real HTTP calls with minimal changes.

---

## 0. Architecture (3 layers)

```
app/
  __init__.py
  config.py               # settings + the ONE Supabase client singleton
  main.py                 # FastAPI wiring: controllers, lifespan, exception handler
  models.py               # request DTOs (pydantic) + row -> camelCase serializers
  deps.py                 # DI graph:  controller --Depends--> service --> repository --> client
  controllers/            # request handling only — parse, call a service, return
    auth.py               #   POST /api/auth/login
    tickets.py            #   /api/tickets CRUD + actions + auto-assign + /api/agents/workload
    attachments.py        #   /api/tickets/{id}/attachment (multipart + signed URL)
    drafts.py             #   /api/drafts CRUD + submit + attachments
    notifications.py      #   /api/notifications list/read/read-all/sweep
    users.py              #   /api/users, /api/users/agents, /api/meta
  services/               # business rules — no HTTP, no database specifics
    ticket_service.py     #   create/list/get/replies, status/priority/category, assign, auto-assign, workload
    draft_service.py      #   draft CRUD, submit validation, attachment swap
    notification_service.py  # pure recipient/message rules + emit + SLA sweep + retention jobs
    user_service.py       #   directory lists + static meta
    auth_service.py       #   GoTrue password grant + account join
  repositories/           # the ONLY layer that touches Supabase
    base.py               #   unwrap/run/rows_of/first_of + SupabaseRepository base
    user_repository.py
    ticket_repository.py  #   tickets + replies (thread) + ref/uuid resolver
    draft_repository.py
    notification_repository.py
    attachment_storage.py #   Storage bucket ops (upload/remove/signed URL, 413/502 mapping)
```

Rules of the layering:

1. **Controllers** never query Supabase and never contain business rules.
2. **Services** contain the store.js-mirroring rules; they build their logic on
   repositories and raise HTTPException only for domain responses (404/409/422).
3. **Repositories** own every `.table(...)` chain and map PostgREST errors to
   400/502 (`Database rejected the write: ...`). They take the client as a
   constructor argument, injected by `app/deps.py` — which is why the offline
   test fake works with a single monkeypatch of `app.config.get_client`.
4. Serializers/DTOs live in `app/models.py` — the HTTP <-> domain contract.

## 1. Put this folder in the project

Save these files into the repo so you end up with:

```
hr-ticketing-system/
  backend/                 (this repo)
    .env.example
    requirements.txt
    schema.sql
    README.md              (this file)
    app/                   (see section 0 above)
  src/ ... (frontend, unchanged)
```

## 2. Create the Supabase project (first time only)

1. Go to https://supabase.com/dashboard and **New project** (any region near you;
   a DB password you can paste once — it is not used by this backend).
2. Wait for provisioning, then open **SQL Editor** (left sidebar, `_`-shaped terminal icon → SQL Editor → New query).
3. Paste the entire contents of `backend/schema.sql` and **Run**. It creates:
   - `users`, `tickets`, `ticket_drafts`, and `replies` tables with constraints
   - a `TKT-<n>` reference generated per row, starting at **TKT-101**
   - an `updated_at` trigger, RLS enabled (server-only access), and the private
     storage bucket `ticket-attachments`
   - seeds your 7 demo users (Priya, Marcus, Dana, Tomas + Alicia, Ben, Ruth)
   - creates private, employee-owned ticket drafts that remain separate from HR tickets
4. Open **Project Settings → API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **service_role secret key** (localStorage "service_role") → `SUPABASE_SERVICE_ROLE_KEY`

> The backend uses the **service_role** key server-side (it bypasses RLS by design).
> Never put this key in frontend code or commit `backend/.env`.

If you already created the Supabase schema before drafts were added, rerun the
current `backend/schema.sql` in the SQL Editor. Its statements are idempotent
and will create the missing `ticket_drafts` table and trigger.

## 3. Configure and run

Requires **Python 3.10+**.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # then paste your URL + service key into .env
uvicorn app.main:app --reload --port 8000
```

- Interactive docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health

## 4. Smoke test (curl) — create a ticket

Grab an employee uuid first:

```bash
curl http://localhost:8000/api/users
```

Then create a ticket:

```bash
curl -X POST http://localhost:8000/api/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "employeeId": "<uuid-from-users-list>",
    "category": "Payroll",
    "priority": "High",
    "subject": "May payslip is missing the shift allowance",
    "description": "The May payslip does not include the 12 hours of weekend shift allowance I worked."
  }'
```

Validation mirrors the frontend: subject ≥ 5 chars, description ≥ 20 chars,
category ∈ {Payroll, Leave, Benefits, Onboarding, Policy, Other},
priority ∈ {Low, Medium, High, Urgent}. `GET /tickets/TKT-101` returns the created row
with its thread (`turns`), or 404 if missing.

## 5. Endpoint map (store.js → API)

| Frontend store function | API endpoint |
| --- | --- |
| `createTicket(...)` | `POST /api/tickets` |
| `listTickets()` | `GET /api/tickets?...` (filters: `status, category, priority, employeeId, assigneeId, q, unassigned`) |
| `getTicket(id)` | `GET /api/tickets/{TKT-n or uuid}` |
| `addReply(ticketId, {...})` | `POST /api/tickets/{id}/replies` (`{ authorId, text }`) |
| `updateStatus(id, status, actorId)` | `PATCH /api/tickets/{id}/status` (`{ status, actorId }`) |
| `assignTicket(id, assigneeId)` | `PATCH /api/tickets/{id}/assignee` (`{ assigneeId: uuid|null }`) |
| `setPriority(id, priority)` | `PATCH /api/tickets/{id}/priority` |
| `setCategory(id, category)` | `PATCH /api/tickets/{id}/category` |
| `USERS` / `HR_AGENTS` / lookups | `GET /api/users`, `GET /api/users/agents`, `GET /api/meta` |
| (attachment file) | `POST /api/tickets/{id}/attachment` (multipart `file`), `GET /api/tickets/{id}/attachment` (signed URL) |

Behaviour copied from the mock store: agent replies stamp `firstReplyAt` once and
move `Open → In Progress`; employee replies flip an active ticket to
`Waiting on Employee`; assigning an unanswered ticket auto-posts the agent
"picked it up" reply; `Resolved` stamps `resolvedAt`; `Closed` records `closedBy`;
reopening clears both.

## 6. Wiring the frontend later

`src/data/store.js` function bodies become `fetch` calls against
`http://localhost:8000/api/...` (JSON bodies use camelCase keys as above).
Users for the login screen come from `GET /api/users` instead of `USERS` — the
mock `u1/h1` ids become the seeded users' Postgres uuids. Until real auth exists,
requests carry the acting user's id (`employeeId`, `authorId`, `actorId`) exactly
like the mock store does today — that is the next hardening step (Supabase Auth
in frontend + FastAPI JWT check).

## 7. Attachments

Files go into the private `ticket-attachments` bucket at `<TKT-ref>/<uuid>.<ext>`
(capped at 5 MB, same as the frontend). Reading one back returns a signed URL
(default 1 h — tune `ATTACHMENT_SIGNED_URL_TTL`). A ticket holds one attachment;
uploading again replaces it.

## 7b. Assignment flows

| Flow | Endpoint | Behaviour |
| --- | --- | --- |
| Manual assign/unassign | `PATCH /api/tickets/{id}/assignee` `{ assigneeId: uuid-or-null }` | validates agent role; auto for unanswered tickets |
| Auto assign (routing) | `POST /api/tickets/{id}/auto-assign` | picks least-loaded agent (`openCount`, tiebreak `totalCount`); 409 if ticket is Resolved/Closed or no agents exist |
| Agent workload | `GET /api/agents/workload` | `[{id, name, email, openCount, totalCount}]` — openCount counts Open/In Progress/Waiting on Employee |

Both assign flows share one core (`TicketService.assign`): assigning an
unanswered ticket posts the agent pickup reply, stamps `firstReplyAt`, and moves
`Open → In Progress`. `routedTo` is appended to the auto-assign response so
callers can show who was chosen.

```bash
curl http://localhost:8000/api/agents/workload
curl -X POST http://localhost:8000/api/tickets/TKT-101/auto-assign
curl -X PATCH http://localhost:8000/api/tickets/TKT-101/assignee \
  -H "Content-Type: application/json" -d '{"assigneeId": "<agent-uuid>"}'
```

## 8. supabase-py gotchas baked into this code

- **Never call `.table("X")` on the result of another `.table("Y")`** — always
  start a fresh chain; every repository method does exactly that.
- **PostgREST response shapes vary by supabase-py version** (APIResponse with
  `.data`, plain lists, single dicts, `(data, count)` tuples). All calls go
  through `run()`/`rows_of()`/`first_of()`/`unwrap()` in `app/repositories/base.py`,
  which normalise every variant. `.execute().data` or `.single()` chains are used
  nowhere else.
- An uncaught exception returns readable JSON (`{"error", "detail"}`) via the
  dev handler in `main.py` and prints the traceback to the console.
- Write this: `.is_("assignee_id", None)` (v2 rejects the string `"null"`), and
  storage uploads use `{"contentType": ..., "upsert": "false"}`.

## 9. Conventions

- All write endpoints return the **full ticket including the thread**, so callers
  can update their local state in one round-trip.
- `/api/tickets` list items have empty `turns` for size — fetch a single ticket
  for the full thread.
- Errors: `404` unknown ticket, `413` file too large, `422` validation/unknown user,
  `400/502` database or storage rejection.

## 10. In-app notifications

Event-driven and channel-agnostic. Ticket writes stay decoupled from
notification logic: services call `safe_notify(...)` on their injected
**NotificationService** (from `app/services/notification_service.py`) **after**
the ticket write completes, and `safe_notify` swallows (and logs) any failure —
a broken notification path can never break a ticket action.

```
ticket service (create/assign/status/reply/draft submit)
   └─> NotificationService.safe_notify(event, ticket, actor, recipients)
         └─> NotificationRepository.insert_rows(...)   (channel='in_app')
Background (FastAPI lifespan, every 30 min)
   ├─> svc.run_sla_sweep(): unassigned tickets past first-response SLA
   └─> svc.run_retention_cleanup(): read >30 days, anything >180 days
```

**Privacy rule:** message text is generic ("`Alicia Gomez assigned TKT-104 to
you`", "`TKT-101 was resolved by Ben Osei`") — no subject, description or reply
body is ever copied into a notification, since HR ticket content is sensitive.

| Event (`type`) | Who gets notified | Notes |
| --- | --- | --- |
| `ticket_created` | all HR agents | fires from `POST /tickets` **and** draft `submit` |
| `ticket_assigned` | new assignee | skipped when re-picking the same agent; clearing notifies nobody |
| `ticket_status_changed` | owner + assignee, minus the actor | `Resolved`/`Closed` word the message accordingly |
| `ticket_reply` | other party, minus the author | employee reply on an *unassigned* ticket also fans out to agents |
| `sla_breached` | all HR agents | Urgent unassigned > 4 h, others > 24 h; **at most once per ticket/threshold** |

### Endpoints (all hard-scoped to the acting `userId`)

| Call | Endpoint |
| --- | --- |
| List (newest-first, `state=unread`, limit/offset) | `GET /api/notifications?userId=&state=all|unread&limit=&offset=` |
| Unread badge | `GET /api/notifications/unread-count?userId=` → `{ "unread": n }` |
| Mark one read | `POST /api/notifications/{id}/read` `{ "userId" }` (404 if not yours) |
| Mark all read | `POST /api/notifications/read-all` `{ "userId" }` → `{ "updated": n }` |
| Run sweep/cleanup now (ops/test) | `POST /api/notifications/sweep` `{ "userId" }` |

`userId` is the mock-auth stand-in for a future JWT/server session — the service
ignores everything except rows whose `recipient_id` equals it, so isolation is
already enforced server-side; the auth gap is tracked under "Wiring the
frontend later".

### Schema + setup

`schema.sql` section 8 is idempotent like the rest — re-run the whole file in the
Supabase SQL editor (creates `public.notifications` + indexes + RLS, no-op parts
stay no-ops). No migration tool; one Supabase project, one idempotent script.

### Adding a new notification type

1. Add the `type` value to the check constraint in `schema.sql` section 8.
2. Add an `EV_*` constant + a message branch in `_message_for` in
   `app/services/notification_service.py`, keeping the text generic.
3. Write a pure recipient rule (`*_recipients`) and unit-test it in
   `tests/unit/test_notification_rules.py`.
4. Call `notifier.safe_notify(ticket, EV_*, actor, recipients(...))` at the
   trigger point in the relevant service — *after* the write succeeds.
5. If the frontend needs a distinct icon, add the `type` → icon path mapping in
   `src/components/NotificationRow.jsx`.

The SLA sweep/interval constants (`SLA_THRESHOLDS_HOURS`, `SLA_SWEEP_INTERVAL_SECONDS`,
`RETENTION_*`) live in `app/services/notification_service.py`.

### Testing

```bash
cd backend && .venv/bin/activate
pytest            # offline: FastSupabase fake, no network (integration is excluded)
pytest -m integration   # live round-trips against the real project
```

## 11. Resilience — circuit breakers

Supabase is the only external dependency and is reached over the network in
three independent places. When one of them is down, overloaded or stalled,
callers used to pay a full network round trip every time — and the failing
service kept getting hammered. Each surface now sits behind a small
(thread-safe, stdlib-only) circuit breaker in `app/resilience.py`, so
outages degrade fast instead of slowly:

```
db_breaker       PostgREST — every repository call funnels through
                 run()/rows_of()/first_of() in app/repositories/base.py
auth_breaker     GoTrue password grant — app/services/auth_service._grant()
storage_breaker  Storage bucket ops — app/repositories/attachment_storage.py
```

States: `closed` (normal) → `open` after N consecutive failures — every call
fails instantly with **503**, nothing touches the network → after the
cooldown ONE half-open probe is admitted; the rest of the concurrent callers
still fail fast (no stampede). Probe success → closed again with counters
reset; probe failure → open for another cooldown. Transitions are logged
under the `hrdesk.resilience` logger.

| Surface | Counts as failure | Never counts (neutral) |
| --- | --- | --- |
| db (PostgREST) | non-`23xxx` APIError (→502 today), transport errors | `23xxx` constraint violations (→400) |
| auth (GoTrue) | transport errors, `AuthApiError` ≥ 500 | answered grant errors (401/403/422) |
| storage | any exception | — (`check_size` runs before any call) |

Neutrality is the point: a caller's own mistake or a bad password proves the
dependency is HEALTHY and must not trip anything. Conversely a neutral error
received on the half-open probe is evidence of life and closes the circuit.

- **Env knobs** (in `app/config.py`): `CIRCUIT_BREAKER_FAILURE_THRESHOLD`
  (default 5), `CIRCUIT_BREAKER_RECOVERY_SECONDS` (default 30). Set the
  threshold huge to effectively disable a breaker during local debugging.
- **Visibility**: `GET /health/deps` (no Supabase calls, answers mid-outage):

  ```json
  {"breakers": {"db": {"name": "db", "state": "open", "failures": 5, "secondsUntilProbe": 12.4},
                "auth": {"name": "auth", "state": "closed", "failures": 0}}}
  ```

- **HTTP behavior while open**: db-backed endpoints →
  `503 {"detail": "Database is temporarily unavailable — try again shortly."}`;
  login → `503 "Authentication service is temporarily unavailable…"`;
  attachments → `503 "Attachment storage is temporarily unavailable…"`.
  The frontend sees immediate 503s and recovers automatically once the probe
  succeeds — no code change needed.
- **Background jobs** (SLA sweep, retention) route through the same `run()`,
  so an open db circuit also stops them from hammering PostgREST every 30
  minutes; failures are already swallowed by their own error handling.
- **Network timeouts** (verified against installed supabase-py 2.32):
  PostgREST 120 s, Storage 20 s, auth uses raw httpx default (5 s). All
  bounded, so a stalled dependency eventually raises and the breaker can
  count it — no extra configuration required. (The 120 s PostgREST ceiling
  is generous for this workload; trimming it via `ClientOptions` would make
  the first few failures trip the breaker faster — future tuning.)
- Test coverage: `tests/unit/test_circuit_breaker.py` (state machine +
  `run()` classification), `tests/unit/test_auth_breaker.py`,
  `tests/api/test_breakers.py` (fail-fast through real endpoints,
  `/health/deps`, surface independence).
