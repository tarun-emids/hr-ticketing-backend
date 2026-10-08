# CLAUDE.md — repositories

The only layer that touches Supabase. base.py holds the shared plumbing and
the gotchas — do not re-solve them per repository.

## supabase-py mechanics (all baked into app/repositories/base.py)

1. **Query builders are single-use.** Never call `.table("X")` on the result
   of a `.table("Y")` chain; every method starts a fresh
   `client.table(name)`.
2. **Never `.execute()` bare.** Every call goes through `run()` /
   `rows_of()` / `first_of()` in base.py, which (a) normalize the response
   envelope across supabase-py versions (APIResponse / list / dict /
   `(data, count)` tuples), (b) map errors — PostgREST constraint codes
   (`23xxx`) → 400, everything else → 502 — and (c) run the call behind the
   `db_breaker` circuit breaker. Precedent: notification_repository used to
   have one bare `.execute()` (delete_row) that bypassed all three; it was
   corrected. A new direct network call here is a bug.
3. NULL checks use `.is_("col", None)` — supabase-py v2 rejects the string
   `"null"`.
4. Storage ops go through `.storage.from_(BUCKET)` with
   `{"contentType": ..., "upsert": "false"}`, and uploads are validated by
   the caller first (`check_size`, 5 MB cap) — 413 never reaches storage.

## Breaker integration rules

- The db breaker counts non-`23xxx` APIError and transport errors;
  constraint violations are NEUTRAL (caller's fault — the database answered).
  Any added failure mode must be classified through `_db_failure` in
  base.py, not invented per call site.
- Storage ops each run behind `storage_breaker` (any exception counts).
  Translate `CircuitOpenError` → `HTTPException(503)` with that surface's
  wording BEFORE the generic `except Exception` clauses.

## Structure

- `SupabaseRepository` holds the client injected via constructor
  (`app/deps.py`); subclasses set `TABLE_NAME` and build intent-revealing
  query methods. Do not import `app.config` inside repository methods — the
  offline tests swap the client by monkeypatching `app.config.get_client`,
  so anything importing it directly breaks injection.
- Ticket lookups resolve either `TKT-<n>` refs or raw uuids through
  `ticket_ref()` (REF_FIELD vs ID_FIELD) — reuse it rather than hand-rolling
  key logic.
- Storage `upload`/`remove`/`signed_url` live on
  `AttachmentStorageRepository` (not a `SupabaseRepository` — different API
  surface, same data-access layer).
