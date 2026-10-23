-- HR Desk PostgreSQL schema. Safe to run repeatedly.

CREATE TABLE IF NOT EXISTS users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL,
  email         text NOT NULL UNIQUE,
  role          text NOT NULL CHECK (role IN ('employee', 'agent')),
  password_hash text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash text;

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

CREATE TABLE IF NOT EXISTS kb_documents (
  slug          text PRIMARY KEY,
  ref           text NOT NULL UNIQUE,
  title         text NOT NULL,
  category      text NOT NULL,
  audience      text NOT NULL CHECK (audience IN ('employee', 'hr')),
  summary       text NOT NULL DEFAULT '',
  keywords      text NOT NULL DEFAULT '',
  search_text   text NOT NULL DEFAULT '',
  file_path     text NOT NULL,
  file_size     bigint NOT NULL CHECK (file_size >= 0),
  page_count    integer NOT NULL CHECK (page_count > 0),
  version       text NOT NULL,
  effective_date date NOT NULL,
  file_data     bytea,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kb_documents_audience_updated
  ON kb_documents (audience, updated_at DESC);

INSERT INTO users (name, email, role) VALUES
  ('Priya Sharma', 'priya@acme.com',     'employee'),
  ('Marcus Webb',  'marcus@acme.com',    'employee'),
  ('Dana Cole',    'dana@acme.com',      'employee'),
  ('Tomas Nowak',  'tomas@acme.com',     'employee'),
  ('Alicia Gomez', 'alicia.hr@acme.com', 'agent'),
  ('Ben Osei',     'ben.hr@acme.com',    'agent'),
  ('Ruth Meyer',   'ruth.hr@acme.com',   'agent')
ON CONFLICT (email) DO NOTHING;
