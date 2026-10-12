# CLAUDE.md — tests

Everything (except `-m integration`) runs offline: no network, no .env
needed, full suite well under 10 s.

## The offline harness (tests/conftest.py)

- `FakeSupabase` emulates the fixed query-builder subset the repositories
  use (select/insert/update/delete + eq/is_/ilike/lt/order/limit), plus
  FakeStorage (with a `fail_uploads` switch) for the attachment surface.
- **Single wiring point:** the `api` fixture monkeypatches
  `app.config.get_client` → the whole DI graph (every repository, every
  request) uses the fake. Build nothing else.
- The `api` fixture seeds 7 demo users (U dict, alicia/ben/ruth are agents)
  and 3 tickets (TKT-101..103) mirroring store.js.
- FK-shaped DB errors come from `tests.conftest._fk_error` (APIError with
  code 23503 → `run()` maps to 400). Note the level split: unknown
  employees are rejected by SERVICE validation as 422 *before* any insert —
  test constraint behavior directly through `base.run()` instead
  (see tests/unit/test_circuit_breaker.py).
- Auth grant errors are duck-typed stubs (class name containing
  "AuthApiError" + .message/.status) — see tests/unit/test_auth_breaker.py.

## Rules

- **Reset breakers**: `app/resilience.py` breakers are process-wide
  singletons. Any module that trips them wires an autouse fixture calling
  `reset()` before/after (pattern in tests/api/test_breakers.py).
  Thresholds come from `app.config` (env knobs, default 5).
- The TestClient is built WITHOUT `with` (conftest `api` fixture) — i.e.
  lifespan never runs, so background SLA/retention jobs are inert in
  offline tests. Keep it that way for determinism; drive job logic through
  the service methods directly if you need them.
- Don't hit the network: anything needing a real Supabase belongs under
  `-m integration` (tests/integration, requires backend/.env + seeded
  schema), never in the default path.
- When adding a fixture or helper, keep conftest.py the single home —
  per-file copies drift.
