-- HR Desk PostgreSQL schema. Safe to run repeatedly.

CREATE TABLE IF NOT EXISTS users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL,
  email         text NOT NULL UNIQUE,
  role          text NOT NULL CHECK (role IN ('employee', 'agent', 'admin')),
  password_hash text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash text;

-- Admin persona upgrade (2026-10): widen the role check in place for
-- databases created before admin existed. Constraint name is the postgres
-- default for an inline CHECK (users_role_check); IF EXISTS keeps reruns safe.
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
  CHECK (role IN ('employee', 'agent', 'admin'));

CREATE TABLE IF NOT EXISTS tickets (
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
);

CREATE INDEX IF NOT EXISTS idx_tickets_updated ON tickets (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets (status);
CREATE INDEX IF NOT EXISTS idx_tickets_employee ON tickets (employee_id);

CREATE TABLE IF NOT EXISTS ticket_drafts (
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
);

CREATE INDEX IF NOT EXISTS idx_ticket_drafts_employee
  ON ticket_drafts (employee_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS replies (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id   uuid NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
  author_id   uuid NOT NULL REFERENCES users (id),
  author_role text NOT NULL CHECK (author_role IN ('employee', 'agent')),
  body        text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 5000),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_replies_ticket ON replies (ticket_id, created_at);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tickets_updated ON tickets;
CREATE TRIGGER trg_tickets_updated
  BEFORE UPDATE ON tickets
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_ticket_drafts_updated ON ticket_drafts;
CREATE TRIGGER trg_ticket_drafts_updated
  BEFORE UPDATE ON ticket_drafts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS notifications (
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
);

CREATE INDEX IF NOT EXISTS idx_notifications_recipient_created
  ON notifications (recipient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient_unread
  ON notifications (recipient_id) WHERE NOT read;
CREATE INDEX IF NOT EXISTS idx_notifications_ticket ON notifications (ticket_id);

CREATE TABLE IF NOT EXISTS attachments (
  path         text PRIMARY KEY,
  data         bytea NOT NULL,
  content_type text NOT NULL DEFAULT 'application/octet-stream',
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- Seeded personas: 1 admin + 3 employees + 3 HR agents (7 accounts).
-- Emails carry no role marker (.hr@) on purpose: a person keeps one address
-- across promotions/demotions — the email is the sign-in identity and only
-- users.role changes. Naming rule: first name, lowercase @acme.com.
-- Legacy `.hr@` accounts (created before this rule) are renamed in place,
-- and a prior run of this file under an intermediate ordering may have left
-- BOTH variants behind (an old `.hr@` plus its freshly seeded twin). The
-- three steps below handle every state idempotently:
--   1/ rename `.hr@` -> clean, but ONLY when the clean address is free
--      (guarded, so a duplicate pair never trips the unique constraint);
--   2/ when both variants DO exist, delete the freshly-seeded twin — but
--      only while it is genuinely unreferenced (the original `.hr@` row
--      may already be pointed at by replies/notifications/assignments);
--      if somebody did real work on the clean login, the delete skips it
--      and the situation must be resolved manually;
--   3/ rename again for whatever the first pass had to skip.
-- After that the seed insert finds clean emails already occupied and skips.
-- One more reminder for existing installs: an account created earlier as
-- 'employee' keeps that role until
--   `python scripts/provision_users.py --admin tomas@acme.com`
-- promotes it (the ON CONFLICT DO NOTHING here never rewrites roles).
UPDATE users SET email = replace(email, '.hr@acme.com', '@acme.com')
WHERE email LIKE '%.hr@acme.com'
  AND NOT EXISTS (
    SELECT 1 FROM users u2
    WHERE u2.email = replace(users.email, '.hr@acme.com', '@acme.com')
  );

DELETE FROM users twin
WHERE twin.email IN (
    SELECT replace(p.email, '.hr@acme.com', '@acme.com')
    FROM users p WHERE p.email LIKE '%.hr@acme.com'
  )
  AND NOT EXISTS (SELECT 1 FROM replies r WHERE r.author_id = twin.id)
  AND NOT EXISTS (
    SELECT 1 FROM tickets t
    WHERE t.employee_id = twin.id OR t.assignee_id = twin.id OR t.closed_by = twin.id
  )
  AND NOT EXISTS (SELECT 1 FROM notifications n WHERE n.recipient_id = twin.id);

UPDATE users SET email = replace(email, '.hr@acme.com', '@acme.com')
WHERE email LIKE '%.hr@acme.com';

INSERT INTO users (name, email, role) VALUES
  ('Priya Sharma', 'priya@acme.com',     'employee'),
  ('Marcus Webb',  'marcus@acme.com',    'employee'),
  ('Dana Cole',    'dana@acme.com',      'employee'),
  ('Tomas Nowak',  'tomas@acme.com',     'admin'),
  ('Alicia Gomez', 'alicia@acme.com',    'agent'),
  ('Ben Osei',     'ben@acme.com',       'agent'),
  ('Ruth Meyer',   'ruth@acme.com',      'agent')
ON CONFLICT (email) DO NOTHING;

-- ------------------------------------------------------------
-- Knowledge base policy documents
--   Metadata and the rendered PDF bytes (`data`) both live here: the
--   API streams the file straight from this table behind the same
--   visibility gate. `audience`:  'employee' -> employee-facing policies;
--   'hr' -> HR-only SOPs (agents see both pools). `search_text` is the
--   lowercased title+category+summary+keywords+body blob scored by
--   app/services/kb_service.py. Rows are upserted by
--   scripts/seed_knowledge_base.py (pre-rendered PDFs in
--   scripts/knowledge_base_pdfs/).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kb_documents (
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
);

CREATE INDEX IF NOT EXISTS idx_kb_documents_audience
  ON kb_documents (audience);
CREATE INDEX IF NOT EXISTS idx_kb_documents_updated
  ON kb_documents (updated_at DESC);

DROP TRIGGER IF EXISTS trg_kb_documents_updated ON kb_documents;
CREATE TRIGGER trg_kb_documents_updated
  BEFORE UPDATE ON kb_documents
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------
-- 1b. HR assistant (RAG) storage — app/rag/
--   kb_document_chunks: one CITABLE paragraph per row, cut from the same
--     block content the policy PDFs render from (app/kb_seed). Retrieval
--     takes place in the app (cosine over `embedding`) — no pgvector needed.
--     Properties: refreshed by scripts/seed_knowledge_base.py alongside the
--     document bytes; audience is copied so role pools filter in SQL.
--   assistant_queries: one AUDIT row per answered question (employee
--     snapshot + question + answer + cited sources). UI never reads it —
--     reopening the assistant always starts clean.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kb_document_chunks (
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
);

CREATE INDEX IF NOT EXISTS idx_kb_document_chunks_audience
  ON kb_document_chunks (audience);

CREATE TABLE IF NOT EXISTS assistant_queries (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id   uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  employee_name text NOT NULL DEFAULT '',
  employee_role text NOT NULL DEFAULT '',
  question      text NOT NULL,
  answer        text NOT NULL,
  sources       jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_assistant_queries_employee
  ON assistant_queries (employee_id, created_at DESC);
