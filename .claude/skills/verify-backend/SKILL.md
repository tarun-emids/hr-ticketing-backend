---
name: verify-backend
description: Verify the HR Desk backend with the offline suite, PostgreSQL integration tests, and a live server smoke test. Use when asked to verify, test, or smoke the backend, or after runtime-affecting changes.
---

# Verify the HR Desk backend

Run every step from the repository root. Report one PASS/FAIL line per step;
stop at the first hard failure and say where it broke.

## Step 0 — environment

- Use the project `.venv`; this codebase requires Python 3.14.
- Linux/WSL: `.venv/bin/python --version`; Windows:
  `.venv\Scripts\python.exe --version`.
- If the environment is missing, create a Python 3.14 venv and install
  `requirements.txt` plus `pytest` and `ruff`.

## Step 1 — static checks and offline suite

```bash
ruff format --check .
ruff check .
python -m pytest
```

Run these with the project venv active. The suite must have zero failures;
integration tests are excluded by default.

## Step 2 — PostgreSQL integration

Requires `.env` with `DATABASE_URL`, a target schema applied with `psql
"$DATABASE_URL" -v ON_ERROR_STOP=1 -f schema.sql`, and provisioned demo users.

```bash
python -m pytest -m integration
```

The suite writes test tickets and attachments, then removes the records it
created. Do not run against a production database.

## Step 3 — live smoke

Start the server on a free port:

```bash
python -m uvicorn app.main:app --port 8030 --log-level warning
```

Then verify:

- `GET /health` returns `{"ok": true}`.
- `GET /health/deps` reports the PostgreSQL breaker closed.
- `GET /api/users` returns the seeded PostgreSQL users.

Stop the server and confirm port 8030 is free.
