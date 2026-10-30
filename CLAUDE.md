# CLAUDE.md — HR Desk API (FastAPI + PostgreSQL backend)

Backend for the HR ticketing system; endpoint shapes mirror the React
frontend's `store.js` 1:1. README.md holds the full API map and PostgreSQL setup
and walkthroughs — this file is operating instructions for working here.

## Commands

```bash
# offline test suite (no network; integration excluded by default)
.venv/Scripts/python.exe -m pytest

# live tests against PostgreSQL (needs .env + seeded schema)
.venv/Scripts/python.exe -m pytest -m integration

# format + lint — mandatory gate on every code change (also auto-run on every
# .py Write/Edit by the PostToolUse hook in .claude/settings.json — see below)
# Windows copy: .venv/Scripts/ruff.exe | WSL repo: source .venv/bin/activate, then plain `ruff`
.venv/Scripts/ruff.exe format .
.venv/Scripts/ruff.exe check .

# server (docs at /docs, liveness at /health, breaker states at /health/deps)
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

`pytest` is **not** in requirements.txt; install it separately in the venv
(dev tools — pytest, ruff, pre-commit, reportlab — are ad-hoc installs only).

## Formatting & linting (ruff — enforced by PostToolUse hook)

`pyproject.toml` at the repo root is the single source of truth: line length
100, 4-space indents, double quotes, isort import ordering with `app` as
first-party, rule set E/W/F/I/B/SIM minus E501 (the formatter owns line
length) and minus B008 (FastAPI's `Depends(...)`-in-default DI pattern).
Formatting target is py314.

Enforcement is mechanical: `.claude/settings.json` runs a PostToolUse hook
(`.claude/hooks/format_py.ps1` on Windows, `format_py.sh` on WSL) after every
Write/Edit; it `ruff format`s the touched `.py` file, applies safe
`ruff check --fix`es, and returns any leftover findings to the model as a
blocking error. One-time adoption (run once after installing ruff):
`ruff format .` + `ruff check . --fix`, then the offline pytest suite;
expect a whitespace/import-order-only diff.

When ruff can't run in-session (sandboxed VMs), hand-conform instead: wrap
comments/docstrings/long strings at ≤100 columns, import blocks stdlib →
external → first-party `app` alphabetically, magic trailing comma (multiline
collections never collapse), keep the current `Optional[X]` type-hint style,
and end the task with the two commands for the user. ruff is the only
formatter — no prettier, no black.

## Environment quirks (check these before debugging anything odd)

- **Python 3.14 only.** Class bodies shadow the builtin `list`
  (`def list(...)` in TicketService) and later sibling methods annotate
  `-> list[dict]` — only 3.14's lazy annotations tolerate that; 3.11 raises
  `TypeError: 'function' object is not subscriptable` on import. Create the
  venv with `py -3.14 -m venv .venv`.
- `.env` must contain `DATABASE_URL` and a persistent
  `ATTACHMENT_SIGNING_KEY`. The signing key must be identical across workers
  and restarts. The file is gitignored; never commit it or echo secrets.
- WinError 10013 on server start = port 8000 already held by another
  uvicorn instance — stop the other one first.
- Run pytest with the project's own `.venv`, not system Python.

## Architecture (strict 3-layer)

```
app/
  controllers/   FastAPI routers: parse request -> call a service -> return
  services/      business rules only (repositories injected; NO database access)
  repositories/  the ONLY layer that executes PostgreSQL SQL
  deps.py        DI graph; pool resolved via app.config.get_database
  resilience.py  PostgreSQL circuit breaker (+ GET /health/deps)
  models.py      pydantic DTOs + row -> camelCase serializers
  config.py      env + shared PostgreSQL pool (lazy get_database())
```

- Controllers never query PostgreSQL; services raise HTTPException only for
  domain responses (404/409/422); repositories own parameterized SQL and map
  PostgreSQL constraint errors to 400 and dependency failures to 502/503.
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
  app/resilience.py with an outcome-classification predicate. PostgreSQL
  constraint errors and bad credentials are neutral outcomes; they must not
  trip the availability breaker.

## Verification workflow

After any code change: `ruff format` + `ruff check` clean first, then the
offline suite green; if behavior is observable at runtime, start the server
and exercise the change (curl the endpoint), watching `/health/deps` for
PostgreSQL-backed paths.
