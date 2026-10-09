---
name: verify-backend
description: Verify the HR Desk backend in one pass — offline test suite, live server smoke, and the circuit-breaker outage drill against a dead Supabase URL. Use when asked to verify, test or smoke the backend, to demo the breakers, or after any runtime-affecting change (endpoints, repositories, resilience, auth).
---

# Verify the HR Desk backend

Run every step from the repo root (the folder that contains `.venv/`).
Report one PASS/FAIL line per step at the end; stop at the first hard
failure and say exactly where it broke.

## Step 0 — environment

- `.venv/Scripts/python.exe` must exist and MUST be Python 3.14 — this
  codebase only imports under 3.14 (lazy class-body annotations). Check
  with `.venv/Scripts/python.exe --version`.
- If missing/wrong: `py -3.14 -m venv .venv` then
  `.venv/Scripts/python.exe -m pip install -r requirements.txt pytest`
  (pytest is NOT in requirements.txt). Never run with system Python.

## Step 1 — offline suite

```
.venv/Scripts/python.exe -m pytest
```

Gate: zero failures (recently 122 passed + 11 deselected — the count
drifts as tests are added, failures are the signal). Integration tests
are excluded by default by pytest.ini.

## Step 2 — live smoke (needs backend/.env)

Start the server in the background on a free port (8000 is often held by
a stale uvicorn → WinError 10013; use 8030 first):

```
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8030 --log-level warning
```

Then:

- `curl http://127.0.0.1:8030/health` → `{"ok": true}` (liveness)
- `curl http://127.0.0.1:8030/health/deps` → all breakers `"state": "closed", "failures": 0`
- `curl http://127.0.0.1:8030/api/users` → HTTP 200 user list

## Step 3 — circuit-breaker outage drill (no .env needed)

Start a second server pointed at an unreachable Supabase with a short
cooldown:

```
SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=demo-not-real \
CIRCUIT_BREAKER_RECOVERY_SECONDS=10 \
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8031 --log-level warning
```

Sequence (expect exact shapes):

1. 5× `curl -X POST .../api/auth/login -H "Content-Type: application/json" -d '{"email":"a@b.com","password":"x"}'`
   → each is a real failed network attempt (~2 s, HTTP 502). The auth
   breaker opens at 5 (log line: `circuit 'auth' open after 5 consecutive failures`).
2. 6th login → **503 in ~0.01 s** (fail-fast proof) with
   `"Authentication service is temporarily unavailable"`.
3. `curl .../health/deps` → `"auth": {"state": "open", "failures": 5, "secondsUntilProbe": <counting down>}`.
4. `sleep 12` (cooldown 10 s), one more login → that request IS the
   recovery probe: ~2 s attempt, 502
   (log: `circuit 'auth' re-opened (probe failed)`).
5. Next login → instant 503 again. Drill complete.

## Step 4 — cleanup

Stop every uvicorn you started (background tasks and stray ports alike),
confirm the ports are free. The drill writes no files; nothing to commit.
