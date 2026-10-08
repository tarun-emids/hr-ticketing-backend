# CLAUDE.md — HR Desk API (FastAPI + Supabase backend)

Backend for the HR ticketing system; endpoint shapes mirror the React
frontend's `store.js` 1:1. README.md holds the full API map, Supabase setup
and walkthroughs — this file is operating instructions for working here.

## Commands

```bash
# offline test suite (no network; integration excluded by default)
.venv/Scripts/python.exe -m pytest

# live tests against real Supabase (needs backend/.env + seeded schema)
.venv/Scripts/python.exe -m pytest -m integration

# server (docs at /docs, liveness at /health, breaker states at /health/deps)
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

`pytest` is **not** in requirements.txt — after creating the venv, install
deps plus pytest explicitly.

## Environment quirks (check these before debugging anything odd)

- **Python 3.14 only.** Class bodies shadow the builtin `list`
  (`def list(...)` in TicketService) and later sibling methods annotate
  `-> list[dict]` — only 3.14's lazy annotations tolerate that; 3.11 raises
  `TypeError: 'function' object is not subscriptable` on import. Create the
  venv with `py -3.14 -m venv .venv`.
- `backend/.env` must exist (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY)
  before the server starts — the lifespan builds the notification service
  eagerly, which resolves the client. The file is gitignored; never commit
  it and never echo the key in output.
- WinError 10013 on server start = port 8000 already held by another
  uvicorn instance — stop the other one first.
- Run pytest with the project's own `.venv`, not system Python.

## Architecture (strict 3-layer)

```
app/
  controllers/   FastAPI routers: parse request -> call a service -> return
  services/      business rules only (repositories injected; NO Supabase)
  repositories/  the ONLY layer that touches Supabase (client injected)
  deps.py        DI graph; client resolved via app.config.get_client at request time
  resilience.py  circuit breakers for db/auth/storage (+ GET /health/deps)
  models.py      pydantic DTOs + row -> camelCase serializers
  config.py      env + the ONE Supabase client singleton (lazy get_client())
```

- Controllers never query Supabase; services raise HTTPException only for
  domain responses (404/409/422); repositories own every `.table()` chain
  and map PostgREST errors to 400/502.
- **`app/routers/` is deliberately-dead tombstone code** — every module
  raises on import, pointing to the real module in `app/controllers/`.
  Never add routes there; controllers are the router layer.
- Layer-specific rules: [app/repositories/CLAUDE.md](app/repositories/CLAUDE.md),
  [app/services/CLAUDE.md](app/services/CLAUDE.md), and
  [tests/CLAUDE.md](tests/CLAUDE.md).

## Conventions

- Conventional commits (`feat:`/`fix:`/`test:`/`docs:`); open PRs as drafts
  first (no `gh` CLI — use the GitHub compare-url flow); never push/merge
  without an explicit user go-ahead.
- Keep user-facing error details generic. HR ticket content (subject,
  description, reply bodies) is sensitive: never copy it into notification
  rows, error messages or API responses.
- Writes return the full ticket incl. its thread; list endpoints keep
  `turns` empty (fetch one ticket for the thread).
- New external dependency ⇒ add a circuit breaker instance in
  app/resilience.py with an outcome-classification predicate, and remember:
  answered-but-wrong client outcomes (bad credentials, constraint
  violations) are NEUTRAL — they must never trip a breaker.

## Verification workflow

After any code change: offline suite green first; if behavior is
observable at runtime, start the server and exercise the change (curl the
endpoint), watching `/health/deps` when touching Supabase paths.
