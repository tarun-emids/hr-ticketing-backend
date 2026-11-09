# HR Desk API — FastAPI + PostgreSQL

The HR Desk backend persists tickets, users, drafts, replies, notifications,
password hashes, and attachment bytes in PostgreSQL. The HTTP contract mirrors
`src/data/store.js` so the React frontend can use the API without reshaping its
ticket data.

## Architecture

```
app/
  config.py               # environment + shared PostgreSQL connection pool
  main.py                 # FastAPI wiring, lifespan, health endpoints
  models.py               # request DTOs + PostgreSQL-row serializers
  deps.py                 # controller -> service -> repository -> pool
  controllers/            # request handling
  services/               # business rules; repositories injected
  repositories/           # parameterized PostgreSQL statements only
```

Controllers parse requests and call services. Services own business rules and
domain errors. Repositories execute parameterized SQL through psycopg 3; the
PostgreSQL schema enforces relationships, checks, generated ticket references,
and update timestamps. Login credentials use bcrypt hashes stored in
`users.password_hash`. Attachment bytes are kept in the `attachments` table
and served only through short-lived HMAC-signed URLs.

## PostgreSQL setup

Use Python 3.14 (the project uses lazy class-body annotations).

### Local stack with Docker

From this directory, run `make up` to build and start the API and a local
PostgreSQL database; then run `make migrate` to bring the schema to the
latest Alembic revision (below). The API is available at
<http://localhost:8000/docs>. Stop only the backend and database with
`make down`; PostgreSQL data persists in a Docker volume across shutdowns.
Start the frontend separately from `../hr-ticketing-frontend` with its own
`make up`. This stack also starts Mailpit at <http://localhost:8025> for
local email inspection.

The credentials and signing key used by this local stack are development-only.
For Gemini assistant access, set `RAG_GEMINI_API_KEY` in this directory's
`.env` file before starting the backend.

### Schema migrations (Alembic)

The database schema is versioned with Alembic — `alembic.ini` plus
`migrations/`. Migrations run against the same `DATABASE_URL` the backend
itself uses: inside the backend container when driven by Make, host-side
when Alembic is run directly (the URL comes from the environment, from
backend/.env, or `alembic -x url=...`).

| Task | Command (from this directory) |
| --- | --- |
| Apply all pending revisions (or after a pull) | `make migrate` |
| Declare a pre-Alembic database as revision 0001, then apply the rest | `make migrate-stamp` then `make migrate` |
| Start a new empty revision | `make migrate-revision m="add hr_notes to tickets"` |
| Show applied / current revision | `docker compose exec backend alembic current` |
| Emit SQL for review without touching the DB | `alembic upgrade head --sql` (offline output) |

Notes:

- **No autogenerate.** Repositories are raw psycopg SQL; there are no ORM
  models, so revisions are written by hand: minimal, reversible DDL
  (upgrade AND downgrade), then `make migrate`.
- **`op.execute()` is the tool**: PostgreSQL DDL is richer than SQLAlchemy's
  expression language — write raw SQL in revisions (one statement per
  `op.execute`, tables before their triggers/indexes).
- **A baseline revision captures what EXISTS, not what's shiny: revision
  0001 is the historical pre-Alembic structure exactly** (no `auth_version`,
  no reset table); everything THIS release adds is a separate, later
  revision (0002). Stamping an old database at 0001 and then `upgrade head`
  therefore brings it fully current. `make migrate-stamp` stamps **0001
  explicitly, never `head`** — stamping head would silently hide every
  future revision from an under-migrated database.
- The historical repair story (`.hr@` renames, duplicate-account collapse,
  role-check widening) is intentionally absent from 0001 — old databases
  were already healed; new ones never need it.
- **Personas/seed data live outside migrations**: `scripts/provision_users.py`,
  `scripts/seed_knowledge_base.py` and `scripts/seed_demo_data.py` remain the
  data owners.
- `schema.sql` mirrors the CURRENT head state (0001 + later revisions) and
  stays in the repository as an emergency hand-applied bootstrap; the compose
  db service no longer auto-applies it — stack startup instead runs
  `migrate-init` (one-shot `alembic upgrade head`) before the demo/kb
  one-shots and the API. `make migrate` runs the same command on demand.

### External PostgreSQL or host-based setup

1. Create a PostgreSQL database and a dedicated application role. Grant it
   access to the database and schema; the backend does not require Supabase,
   PostgREST, GoTrue, or Supabase Storage.
2. From the repository root, create the schema with Alembic:

   ```bash
   alembic upgrade head    # URL from DATABASE_URL/.env; -x url=… to override
   ```

   This creates the application tables (including PostgreSQL storage for
   attachments and knowledge-base PDFs), indexes, and triggers.
   [`schema.sql`](./schema.sql) is retained in the repository as an
   emergency hand-applied bootstrap:
   `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f schema.sql` produces the same
   head-state structure today; afterwards run
   `alembic stamp 0001 && alembic upgrade head` so Alembic records the
   position (the 0002 guards are no-ops there, but future revisions apply
   normally).
3. Create `.env` from `.env.example`. Configure a PostgreSQL connection URL and
   a persistent attachment signing key:

   ```dotenv
   DATABASE_URL=postgresql://hrdesk:password@localhost:5432/hrdesk
   ATTACHMENT_SIGNING_KEY=<output-of-openssl-rand-hex-32>
   AUTH_SIGNING_KEY=<output-of-openssl-rand-hex-32>
   ```

   Generate each key with `openssl rand -hex 32`. Keep them private and
   identical across all workers and restarts; changing the auth key invalidates
   login tokens. Mailpit's default SMTP endpoint is `127.0.0.1:1025`; configure
   `MAILPIT_HOST` and `MAILPIT_PORT` to match your local Mailpit service.
   For hosted PostgreSQL, use the provider's SSL-enabled connection URL. Pool
   size can be tuned with `DB_POOL_MIN_SIZE` and `DB_POOL_MAX_SIZE`.
4. Install and run:

   ```bash
   python -m venv .venv
   source .venv/bin/activate       # Windows: .venv\Scripts\activate
   python -m pip install --upgrade pip     # avoids stale-global-pkg conflict errors
   pip install -r requirements.txt pytest   # pytest & ruff are dev tools, ad hoc
   python scripts/provision_users.py
   uvicorn app.main:app --reload --port 8000
   ```

   The provisioning command sets an initial password for every account. Use
   `--password` or `HR_DESK_TEMP_PASSWORD` to provide it non-interactively.
   Passwords must contain at least 12 characters and no more than 72 UTF-8
   bytes (bcrypt's input limit). Do not commit `.env` or supply passwords as
   command-line arguments in shared shell history.
   To seed the policy library and render its PDFs into PostgreSQL, install
   `scripts/requirements-seed.txt` and run
   `python scripts/seed_knowledge_base.py`.

- API docs: <http://localhost:8000/docs>
- Liveness: `GET /health` (does not query PostgreSQL)
- PostgreSQL breaker state: `GET /health/deps`

## Knowledge base documents (PostgreSQL)

Policy PDFs live **inside the `kb_documents` table** (metadata + `data`
bytea); the `/api/kb/{slug}/file` endpoint streams them to the browser after
the same viewer/role gate as the metadata endpoints. To load the 30
pre-rendered documents (data lives in `scripts/knowledge_base_pdfs/`):

```bash
# revision 0001 (applied above) creates the kb_documents table
python scripts/seed_knowledge_base.py --dry-run   # plan only
python scripts/seed_knowledge_base.py             # upsert all 30 by slug
python scripts/seed_knowledge_base.py --only leave
```

Re-runs are idempotent (existing slugs are updated in place, new ones
inserted), so it is safe after any schema or wording change. Remove or
replace rows by editing `scripts/knowledge_base_pdfs/` + re-running the
loader. Public per-document metadata (title, audience pools, keywords,
search blob) comes from `app/kb_seed/`.

## HR assistant (RAG over the knowledge base)

`app/rag/` implements the floating HR-assistant chat: questions are answered
from the policy library with mandatory citations. One file per concern:

| File | Concern |
| --- | --- |
| `settings.py` | env knobs (token/model/URLs/top-k) — `RAG_HF_TOKEN` empty = assistant answers "not configured" |
| `chunking.py` | pure rules: knowledge blocks -> citable paragraph chunks with `[REF ¶n]` labels |
| `embeddings.py` | Hugging Face feature-extraction + in-Python cosine ranking (no pgvector) |
| `llm.py` | Hugging Face chat-completions (OpenAI-compatible router) |
| `repository.py` | SQL: read citation chunks + write `assistant_queries` audit rows |
| `service.py` | retrieval -> prompt -> `[REF ¶block]` reconciliation -> sources footer -> audit |
| `controller.py` | `POST /api/assistant/ask` (`{employeeId, question}` -> `{id, answer, citations}`) |

Data model (schema.sql): `kb_document_chunks` — one citable paragraph per
`kb_documents` row, embedded at SEED time; `assistant_queries` — employee
snapshot + question + answer + cited sources. The audit table is never read
back by the UI: closing the assistant window resets the conversation by design.

Citations are enforced in the service, not begged from the model: markers
(`[KB-E-01 ¶7]`) are parsed and matched against chunks the retrieval actually
offered, then a `Sources:` footer naming every used paragraph is appended to
every answer. Role pools filter retrieval exactly like the KB itself
(employee -> employee policies; agents see both pools) — resolved server-side
so editing requests cannot widen visibility.

The Hugging Face upstream is its own circuit breaker (`assistant` in
`GET /health/deps`), with neutral handling for token/model errors, so a flaky
free tier degrades like any other dependency.

### Configure

1. `.env` (see `.env.example`): `RAG_HF_TOKEN=<free token from
   huggingface.co/settings/tokens>`; fine-tune `RAG_CHAT_MODEL` (any model
   your token can serve) and `RAG_TOP_K` if needed.
2. Seeding adds the paragraph chunks automatically
   (`python scripts/seed_knowledge_base.py`; use `--skip-chunks` for
   PDFs-only or run without the token to skip embedding).

### Smoke test

```bash
curl -X POST http://localhost:8000/api/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"employeeId": "<uuid>", "question": "How many PTO days carry over?"}'
# {"id": "...", "answer": "Five PTO days carry over. [KB-E-01 ¶4]\n\nSources:\nKB-E-01 ¶4 — ...",
#  "citations": [{"ref": "KB-E-01", "slug": "leave-and-time-off-policy", "blockNo": 4, ...}]}
```

## Moving existing Supabase data

Supabase's relational tables are PostgreSQL tables and can be exported with
`pg_dump`. For a new, empty target database:

1. Create the schema on the target with Alembic (`alembic upgrade head`,
   or `schema.sql` + a follow-up `alembic stamp 0001` for a hand-applied
   bootstrap).
2. Truncate the seeded rows in the target before importing:

   ```sql
   TRUNCATE notifications, replies, ticket_drafts, tickets, users
   RESTART IDENTITY CASCADE;
   ```

3. Export/import the relational tables. Obtain the source PostgreSQL connection
   URL from the existing provider and keep it in an environment variable:

   ```bash
   pg_dump "$SOURCE_DATABASE_URL" --data-only --no-owner --no-privileges \
     -t public.users -t public.tickets -t public.ticket_drafts \
     -t public.replies -t public.notifications \
     | psql "$DATABASE_URL" -v ON_ERROR_STOP=1
   ```

4. Set new login passwords with `python scripts/provision_users.py`. Supabase
   Auth password hashes are not stored in `public.users` and cannot be reused
   by this database-backed login.
5. Existing Supabase Storage objects are separate from PostgreSQL table data.
   Export and migrate any ticket attachment bytes into `attachments.data`.
   The policy PDFs can be regenerated and seeded into `kb_documents.file_data`
   with `python scripts/seed_knowledge_base.py`.
6. Restore the ticket reference sequence after importing existing ticket
   numbers:

   ```sql
   SELECT setval(
     pg_get_serial_sequence('tickets', 'number'),
     COALESCE((SELECT max(number) FROM tickets), 101),
     EXISTS (SELECT 1 FROM tickets)
   );
   ```

7. Verify row counts and the API before switching the frontend to this backend.

Never run the truncate/import steps against a database containing data you
need to keep. Back up both the source tables and Storage objects first.

## API behavior

response shapes are stable, with two deliberate updates: ticket reads are scoped by the viewer (Phase 1) and `GET api/tickets` returns a paginated envelope (below).

| Frontend operation | Endpoint |
| --- | --- |
| Login | `POST /api/auth/login` |
| Request a password-reset OTP | `POST /api/auth/forgot-password` |
| Reset password with OTP | `POST /api/auth/reset-password` |
| Change password while signed in | `POST /api/auth/password` |
| Create/list tickets | `POST /api/tickets`, `GET /api/tickets?...` (bearer-gated; paginated envelope) |
| Get ticket by reference or UUID | `GET /api/tickets/{TKT-n or uuid}` |
| Add reply | `POST /api/tickets/{id}/replies` |
| Update status / assignee / priority / category | `PATCH /api/tickets/{id}/status`, `/assignee`, `/priority`, `/category` |
| Auto-assign and agent workload | `POST /api/tickets/{id}/auto-assign`, `GET /api/agents/workload` |
| Ticket attachment upload / signed URL | `POST` and `GET /api/tickets/{id}/attachment` |
| Draft CRUD, submit, attachments | `/api/drafts` |
| Notifications | `/api/notifications` |
| Users and lookup metadata | `GET /api/users`, `/api/users/agents`, `/api/meta` |
| Knowledge-base catalogue and policy PDFs | `/api/kb`, `/api/kb/{slug}`, `/api/kb/{slug}/file` |
### GET /tickets
`viewerId` (required uuid), optional filters `status|category|priority|employeeId|assigneeId|unassigned|q`,
paging `page` (>=1, default 1) and `pageSize` (1..100, default 25), sorting
`sort` (updated|created|priority|subject, default updated) and `order` (asc|desc, default desc).

Response is always an envelope:
{
  "items": [ticket…], "page": 1, "pageSize": 25, "total": <exact scoped
  count>, "hasNext": <bool — page*pageSize < total>
}
Rows are sorted by the whitelisted expression then `updated_at DESC, number DESC`
 (tie-broken, stable pages). Row scope = the server-resolved viewer's role
 (employee: own tickets; agent/admin: all). Legacy array response removed in
 Phase 2 — consumers must read `items`.

Ticket writes return the full ticket and thread; ticket lists leave `turns`
empty. Agent replies stamp `firstReplyAt` once and move `Open` tickets to
`In Progress`; employee replies move active tickets to `Waiting on Employee`.
Assigning an unanswered ticket posts the pickup reply. `Resolved` and `Closed`
timestamps and reopen behavior are unchanged.

Attachment upload remains capped at 5 MB. `GET /api/tickets/{id}/attachment`
returns `{name, size, url, expiresInSeconds}`; the URL points back to the API
and is valid for 60 seconds to 24 hours (default one hour). Draft attachment
URLs are similarly scoped to the employee-owned draft.

Login returns an expiring bearer access token. Send it as
`Authorization: Bearer <accessToken>` to API endpoints; account and
knowledge-base administration checks the authenticated database account's
admin role rather than trusting a caller-supplied actor ID. There is no public
signup route: admins create accounts through `POST /api/admin/accounts`.
All new passwords and reset OTPs use bcrypt; existing scrypt password hashes
are upgraded after a successful login when they fit bcrypt's 72-byte limit.
All `/api` endpoints require a valid bearer token except login and the public
forgot/reset-password endpoints. Forgot-password requests return the same
response for existing and unknown emails. For an existing account, the API
emails a six-digit OTP through
Mailpit, valid for 10 minutes by default and limited to five guesses. Changing
or resetting a password invalidates previously issued access tokens.

## Notifications

Notifications are generic and never include ticket subjects, descriptions, or
reply content. Events cover ticket creation, assignment, status changes,
replies, and SLA breaches. Lists and read operations are always scoped to the
requested recipient. The background scheduler runs the SLA sweep and retention
cleanup every 30 minutes.

## Resilience and errors

Every PostgreSQL operation uses one connection pool and the shared database
circuit breaker. Connection/resource outages count toward opening the breaker;
constraint violations and invalid SQL/client errors do not. Open circuits fail
fast with HTTP 503. `GET /health/deps` reports the breaker without querying
PostgreSQL.

Transient PostgreSQL failures are retried with full-jitter exponential
backoff. Reads and idempotent updates/deletes may retry connection/resource
failures; inserts retry only when PostgreSQL reports a transaction-aborting
transient SQLSTATE. Tune attempts and delays with `RETRY_MAX_ATTEMPTS`,
`RETRY_BACKOFF_INITIAL_S`, and `RETRY_BACKOFF_MAX_S`; breaker threshold and
cooldown use `CIRCUIT_BREAKER_FAILURE_THRESHOLD` and
`CIRCUIT_BREAKER_RECOVERY_SECONDS`.

## Verification

```bash
ruff format .
ruff check .
pytest
pytest -m integration       # requires DATABASE_URL and a migrated schema
                            # (alembic upgrade head, or schema.sql + stamp)
```
