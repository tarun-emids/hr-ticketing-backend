# CLAUDE.md — repositories

Repositories are the only layer that executes PostgreSQL statements. Shared
pool access, parameterized SQL execution, breaker handling, and row mapping
live in `app/repositories/base.py`.

## Database access

- Use psycopg parameter placeholders (`%s`) for all values. Never interpolate
  user-controlled values into SQL.
- Table and column names in the generic `insert_row` / `update_row` helpers
  are validated identifiers. Keep dynamic columns constrained to internal
  service fields.
- Route every statement through `run`, `rows_of`, `first_of`, `insert_row`,
  or `update_row` so database spans, circuit breaking, and error mapping stay
  consistent.
- Constraint/data errors map to HTTP 400 and are neutral for the breaker.
  Connection/resource failures map to 502 and count toward the breaker.
- Repositories receive the shared connection pool from `app/deps.py`; never
  import configuration or create a pool in a repository.

## Attachments

`AttachmentStorageRepository` stores file bytes in PostgreSQL and signs
time-limited download links with `ATTACHMENT_SIGNING_KEY`. Validate the 5 MB
limit before inserting bytes. Do not log attachment content or signed tokens.

## Structure

- Ticket references resolve through `ticket_ref()` in `ticket_repository.py`;
  reuse it for `TKT-<n>` and UUID lookups.
- `schema.sql` is the source of truth for table relationships, indexes,
  constraints, generated references, and update triggers.
