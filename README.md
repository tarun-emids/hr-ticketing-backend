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
and update timestamps. Login credentials use salted scrypt hashes stored in
`users.password_hash`. Attachment bytes are kept in the `attachments` table
and served only through short-lived HMAC-signed URLs.

## PostgreSQL setup

Use Python 3.14 (the project uses lazy class-body annotations).

1. Create a PostgreSQL database and a dedicated application role. Grant it
   access to the database and schema; the backend does not require Supabase,
   PostgREST, GoTrue, or Supabase Storage.
2. From the repository root, apply [`schema.sql`](./schema.sql):

   ```bash
   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f schema.sql
   ```

   This idempotently creates the application tables, indexes, triggers, and
   seven demo users.
3. Create `.env` from `.env.example`. Configure a PostgreSQL connection URL and
   a persistent attachment signing key:

   ```dotenv
   DATABASE_URL=postgresql://hrdesk:password@localhost:5432/hrdesk
   ATTACHMENT_SIGNING_KEY=<output-of-openssl-rand-hex-32>
   ```

   Generate the key with `openssl rand -hex 32`. Keep it private and identical
   across all workers and restarts; existing signed URLs become invalid if it
   changes. For hosted PostgreSQL, use the provider's SSL-enabled connection
   URL. Pool size can be tuned with `DB_POOL_MIN_SIZE` and `DB_POOL_MAX_SIZE`.
4. Install and run:

   ```bash
   python -m venv .venv
   source .venv/bin/activate       # Windows: .venv\Scripts\activate
   pip install -r requirements.txt pytest
   python scripts/provision_users.py
   uvicorn app.main:app --reload --port 8000
   ```

   The provisioning command sets an initial password for every account. Use
   `--password` or `HR_DESK_TEMP_PASSWORD` to provide it non-interactively.
   Passwords must contain at least 12 characters. Do not commit `.env` or
   supply passwords as command-line arguments in shared shell history.

- API docs: <http://localhost:8000/docs>
- Liveness: `GET /health` (does not query PostgreSQL)
- PostgreSQL breaker state: `GET /health/deps`

## Knowledge base documents (PostgreSQL)

Policy PDFs live **inside the `kb_documents` table** (metadata + `data`
bytea); the `/api/kb/{slug}/file` endpoint streams them to the browser after
the same viewer/role gate as the metadata endpoints. To load the 30
pre-rendered documents (data lives in `scripts/knowledge_base_pdfs/`):

```bash
# schema.sql (run once, above) creates the kb_documents table
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

1. Apply this repository's `schema.sql` to the target.
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
5. Supabase Storage objects are separate from PostgreSQL table data. Export
   the old private bucket files and re-upload them to the new API, or plan a
   dedicated object migration before cutover. Existing attachment metadata
   alone does not copy the underlying file bytes.
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

The API paths and JSON response shapes remain the same:

| Frontend operation | Endpoint |
| --- | --- |
| Login | `POST /api/auth/login` |
| Create/list tickets | `POST /api/tickets`, `GET /api/tickets?...` |
| Get ticket by reference or UUID | `GET /api/tickets/{TKT-n or uuid}` |
| Add reply | `POST /api/tickets/{id}/replies` |
| Update status / assignee / priority / category | `PATCH /api/tickets/{id}/status`, `/assignee`, `/priority`, `/category` |
| Auto-assign and agent workload | `POST /api/tickets/{id}/auto-assign`, `GET /api/agents/workload` |
| Ticket attachment upload / signed URL | `POST` and `GET /api/tickets/{id}/attachment` |
| Draft CRUD, submit, attachments | `/api/drafts` |
| Notifications | `/api/notifications` |
| Users and lookup metadata | `GET /api/users`, `/api/users/agents`, `/api/meta` |

Ticket writes return the full ticket and thread; ticket lists leave `turns`
empty. Agent replies stamp `firstReplyAt` once and move `Open` tickets to
`In Progress`; employee replies move active tickets to `Waiting on Employee`.
Assigning an unanswered ticket posts the pickup reply. `Resolved` and `Closed`
timestamps and reopen behavior are unchanged.

Attachment upload remains capped at 5 MB. `GET /api/tickets/{id}/attachment`
returns `{name, size, url, expiresInSeconds}`; the URL points back to the API
and is valid for 60 seconds to 24 hours (default one hour). Draft attachment
URLs are similarly scoped to the employee-owned draft.

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

## Verification

```bash
ruff format .
ruff check .
pytest
pytest -m integration       # requires DATABASE_URL and schema.sql
```
