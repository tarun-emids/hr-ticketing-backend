# Supabase to PostgreSQL migration notes

The backend now uses psycopg 3 and a PostgreSQL connection pool directly.
Supabase is no longer needed at runtime: data access is SQL, login hashes are
stored in `users.password_hash`, and attachment bytes are stored in
`attachments.data`.

## Deploying the new backend

1. Provision PostgreSQL and apply [`schema.sql`](./schema.sql).
2. Configure `DATABASE_URL` and a stable `ATTACHMENT_SIGNING_KEY` in `.env`.
3. Install the updated `requirements.txt`.
4. If bringing over existing records, follow the export/import and backup
   instructions in README's **Moving existing Supabase data** section before
   starting the new backend.
5. Run `python scripts/provision_users.py` to issue new initial credentials.
   Supabase Auth credentials cannot be carried over because their hashes are
   managed separately from the application tables.
6. Re-export existing ticket-attachment bytes from Supabase Storage; `pg_dump`
   does not include those objects. Policy PDFs can be regenerated and seeded
   into PostgreSQL with `python scripts/seed_knowledge_base.py`.
7. Run the offline test suite, then `pytest -m integration` against the target
   database before switching the frontend.

For the setup, endpoint contract, and recovery details, see [`README.md`](./README.md).
