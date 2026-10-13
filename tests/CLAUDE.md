# CLAUDE.md — tests

The default suite runs offline against an in-memory SQLite test double;
integration tests (`-m integration`) use PostgreSQL configured by `DATABASE_URL`.

## Offline harness

- `tests/conftest.py` provides `SQLitePool`, implementing the connection-pool
  surface repositories use (`connection()` and parameterized SQL execution).
- **Single wiring point:** the `api` fixture monkeypatches
  `app.config.get_database`; the whole dependency graph uses that pool.
- The fixture seeds seven demo users (U dict, alicia/ben/ruth are agents) and
  three tickets (TKT-101..103) mirroring `store.js`.
- Direct SQL snapshots in individual tests should use `api.fake.execute()`;
  endpoint behavior should go through `api.client`.
- Authentication tests use real scrypt hashing helpers but no database or
  network. The API fixture itself leaves password hashes unprovisioned.

## Rules

- **Reset breakers**: `app/resilience.py` breakers are process-wide
  singletons. Any module that trips them wires an autouse fixture calling
  `reset()` before/after. Thresholds come from `app.config` (default 5).
- The TestClient is built without a lifespan context, keeping background
  SLA/retention jobs inert in offline tests.
- Don't hit an external database in the default path. Real PostgreSQL tests
  belong under `-m integration` and require an explicitly configured
  `DATABASE_URL` plus the seeded `schema.sql`.
- Keep common fixtures and helpers in `tests/conftest.py`.
