"""HR Desk initial schema — faithful port of the pre-Alembic schema.sql DDL.

Revision ID: 0001
Revises: None
Create Date: 2026-11-04

Baselines the whole HR Desk schema so that from here on every schema change
is a new Alembic revision (`make migrate-revision`), applied with
`make migrate`.

Scope notes:
  * Tables, constraints, identity/generated columns, indexes, the
    `set_updated_at` trigger function and its three triggers — exactly what
    schema.sql created on a fresh database, in the same order, with the same
    object names and constraint names (Postgres defaults, e.g.
    `users_role_check`), so a fresh Alembic database is structurally
    identical to a fresh `psql -f schema.sql` database.
  * The stepwise repairs/renames of the historical schema.sql events
    (`.hr@` email renames, duplicate-account collapse, role-check widening)
    are NOT in here — those healed databases created before 2026-10; a
    database that has been stamped/migrated past 0001 was already healed.
  * Personas are NOT seeded here — `scripts/provision_users.py` owns
    account creation. `scripts/seed_knowledge_base.py` and
    `scripts/seed_demo_data.py` own their data.
  * schema.sql stays in the repository as an emergency hand-applied
    bootstrap and as the reference for this revision; the compose db service
    no longer mounts it. Databases that predate Alembic run
    `make migrate-stamp` once to declare themselves current.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# One statement per item, in schema.sql's original creation order (keep the
# order on future inserts: tables before their dependents, triggers after
# their tables, so the SQL in this file can always be replayed top-to-bottom).
INITIAL_SCHEMA = [
    # -- accounts ----------------------------------------------------------
    """
    CREATE TABLE users (
      id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      name          text NOT NULL,
      email         text NOT NULL UNIQUE,
      role          text NOT NULL CHECK (role IN ('employee', 'agent', 'admin')),
      password_hash text,
      auth_version  integer NOT NULL DEFAULT 0,
      created_at    timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE password_reset_otps (
      user_id    uuid PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
      otp_hash   text NOT NULL,
      expires_at timestamptz NOT NULL,
      attempts   integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    # -- tickets -----------------------------------------------------------
    """
    CREATE TABLE tickets (
      id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      number          bigint GENERATED ALWAYS AS IDENTITY (START WITH 101),
      ref             text GENERATED ALWAYS AS ('TKT-' || number::text) STORED UNIQUE,
      employee_id     uuid NOT NULL REFERENCES users (id),
      category        text NOT NULL
                      CHECK (category IN ('Payroll','Leave','Benefits','Onboarding','Policy','Other')),
      subject         text NOT NULL CHECK (char_length(subject) BETWEEN 5 AND 200),
      description     text NOT NULL CHECK (char_length(description) BETWEEN 20 AND 10000),
      priority        text NOT NULL DEFAULT 'Medium'
                      CHECK (priority IN ('Low','Medium','High','Urgent')),
      status          text NOT NULL DEFAULT 'Open'
                      CHECK (status IN ('Open','In Progress','Waiting on Employee','Resolved','Closed')),
      assignee_id     uuid REFERENCES users (id),
      created_at      timestamptz NOT NULL DEFAULT now(),
      updated_at      timestamptz NOT NULL DEFAULT now(),
      first_reply_at  timestamptz,
      resolved_at     timestamptz,
      closed_by       uuid REFERENCES users (id),
      attachment_path text,
      attachment_name text,
      attachment_size bigint
    )
    """,
    """
    CREATE INDEX idx_tickets_updated ON tickets (updated_at DESC)
    """,
    """
    CREATE INDEX idx_tickets_status ON tickets (status)
    """,
    """
    CREATE INDEX idx_tickets_employee ON tickets (employee_id)
    """,
    """
    CREATE TABLE ticket_drafts (
      id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      employee_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      category        text NOT NULL DEFAULT 'Other'
                      CHECK (category IN ('Payroll','Leave','Benefits','Onboarding','Policy','Other')),
      subject         text NOT NULL DEFAULT '',
      description     text NOT NULL DEFAULT '',
      priority        text NOT NULL DEFAULT 'Medium'
                      CHECK (priority IN ('Low','Medium','High','Urgent')),
      created_at      timestamptz NOT NULL DEFAULT now(),
      updated_at      timestamptz NOT NULL DEFAULT now(),
      attachment_path text,
      attachment_name text,
      attachment_size bigint
    )
    """,
    """
    CREATE INDEX idx_ticket_drafts_employee
      ON ticket_drafts (employee_id, updated_at DESC)
    """,
    """
    CREATE TABLE replies (
      id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      ticket_id   uuid NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
      author_id   uuid NOT NULL REFERENCES users (id),
      author_role text NOT NULL CHECK (author_role IN ('employee', 'agent')),
      body        text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 5000),
      created_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX idx_replies_ticket ON replies (ticket_id, created_at)
    """,
    # -- updated_at bookkeeping (function + the triggers it serves; the
    #    kb_documents trigger is created after kb_documents further down,
    #    mirroring schema.sql's order) -------------------------------
    r"""
    CREATE OR REPLACE FUNCTION set_updated_at()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      NEW.updated_at = now();
      RETURN NEW;
    END;
    $$
    """,
    """
    CREATE TRIGGER trg_tickets_updated
      BEFORE UPDATE ON tickets
      FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """,
    """
    CREATE TRIGGER trg_ticket_drafts_updated
      BEFORE UPDATE ON ticket_drafts
      FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """,
    # -- notifications -----------------------------------------------------
    """
    CREATE TABLE notifications (
      id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      recipient_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      ticket_id    uuid REFERENCES tickets (id) ON DELETE CASCADE,
      ticket_ref   text,
      type         text NOT NULL
                   CHECK (type IN ('ticket_created','ticket_assigned','ticket_status_changed',
                                   'ticket_reply','sla_breached')),
      channel      text NOT NULL DEFAULT 'in_app',
      actor_name   text,
      payload      jsonb NOT NULL DEFAULT '{}'::jsonb,
      message      text NOT NULL,
      read         boolean NOT NULL DEFAULT false,
      created_at   timestamptz NOT NULL DEFAULT now(),
      read_at      timestamptz
    )
    """,
    """
    CREATE INDEX idx_notifications_recipient_created
      ON notifications (recipient_id, created_at DESC)
    """,
    """
    CREATE INDEX idx_notifications_recipient_unread
      ON notifications (recipient_id) WHERE NOT read
    """,
    """
    CREATE INDEX idx_notifications_ticket ON notifications (ticket_id)
    """,
    # -- attachment storage --------------------------------------------------
    """
    CREATE TABLE attachments (
      path         text PRIMARY KEY,
      data         bytea NOT NULL,
      content_type text NOT NULL DEFAULT 'application/octet-stream',
      created_at   timestamptz NOT NULL DEFAULT now()
    )
    """,
    # -- knowledge base (README §4) -----------------------------------------
    """
    CREATE TABLE kb_documents (
      id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      slug           text NOT NULL UNIQUE,
      ref            text,
      title          text NOT NULL,
      category       text NOT NULL DEFAULT 'General',
      audience       text NOT NULL CHECK (audience IN ('employee', 'hr')),
      summary        text NOT NULL DEFAULT '',
      keywords       text NOT NULL DEFAULT '',
      search_text    text NOT NULL DEFAULT '',
      data           bytea NOT NULL,
      content_type   text NOT NULL DEFAULT 'application/pdf',
      file_size      bigint,
      page_count     int,
      version        text NOT NULL DEFAULT 'v1.0',
      effective_date date,
      created_at     timestamptz NOT NULL DEFAULT now(),
      updated_at     timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX idx_kb_documents_audience
      ON kb_documents (audience)
    """,
    """
    CREATE INDEX idx_kb_documents_updated
      ON kb_documents (updated_at DESC)
    """,
    """
    CREATE TRIGGER trg_kb_documents_updated
      BEFORE UPDATE ON kb_documents
      FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """,
    # -- HR assistant (RAG) storage (app/rag/) -------------------------------
    """
    CREATE TABLE kb_document_chunks (
      id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      document_id   uuid NOT NULL REFERENCES kb_documents (id) ON DELETE CASCADE,
      document_slug text NOT NULL,
      ref           text NOT NULL,
      title         text NOT NULL,
      audience      text NOT NULL CHECK (audience IN ('employee', 'hr')),
      section       text NOT NULL DEFAULT '',
      block_no      int NOT NULL,
      body          text NOT NULL,
      embedding     jsonb NOT NULL,
      created_at    timestamptz NOT NULL DEFAULT now(),
      UNIQUE (document_slug, block_no)
    )
    """,
    """
    CREATE INDEX idx_kb_document_chunks_audience
      ON kb_document_chunks (audience)
    """,
    """
    CREATE TABLE assistant_queries (
      id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      employee_id   uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      employee_name text NOT NULL DEFAULT '',
      employee_role text NOT NULL DEFAULT '',
      question      text NOT NULL,
      answer        text NOT NULL,
      sources       jsonb NOT NULL DEFAULT '[]'::jsonb,
      created_at    timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX idx_assistant_queries_employee
      ON assistant_queries (employee_id, created_at DESC)
    """,
]

# Reverse of creation order: indexes/triggers/functions named explicitly so
# the drop never relies on CASCADE surprises; FK dependencies stay safe —
# dependent tables drop before the tables they reference (users last).
DOWNGRADE_STATEMENTS = [
    "DROP INDEX IF EXISTS idx_assistant_queries_employee",
    "DROP TABLE IF EXISTS assistant_queries",
    "DROP INDEX IF EXISTS idx_kb_document_chunks_audience",
    "DROP TABLE IF EXISTS kb_document_chunks",
    "DROP TRIGGER IF EXISTS trg_kb_documents_updated ON kb_documents",
    "DROP INDEX IF EXISTS idx_kb_documents_updated",
    "DROP INDEX IF EXISTS idx_kb_documents_audience",
    "DROP TABLE IF EXISTS kb_documents",
    "DROP TABLE IF EXISTS attachments",
    "DROP INDEX IF EXISTS idx_notifications_ticket",
    "DROP INDEX IF EXISTS idx_notifications_recipient_unread",
    "DROP INDEX IF EXISTS idx_notifications_recipient_created",
    "DROP TABLE IF EXISTS notifications",
    "DROP TRIGGER IF EXISTS trg_ticket_drafts_updated ON ticket_drafts",
    "DROP TRIGGER IF EXISTS trg_tickets_updated ON tickets",
    "DROP FUNCTION IF EXISTS set_updated_at()",
    "DROP INDEX IF EXISTS idx_replies_ticket",
    "DROP TABLE IF EXISTS replies",
    "DROP INDEX IF EXISTS idx_ticket_drafts_employee",
    "DROP TABLE IF EXISTS ticket_drafts",
    "DROP INDEX IF EXISTS idx_tickets_employee",
    "DROP INDEX IF EXISTS idx_tickets_status",
    "DROP INDEX IF EXISTS idx_tickets_updated",
    "DROP TABLE IF EXISTS tickets",
    "DROP TABLE IF EXISTS password_reset_otps",
    "DROP TABLE IF EXISTS users",
]


def upgrade() -> None:
    for statement in INITIAL_SCHEMA:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
